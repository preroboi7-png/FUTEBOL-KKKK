import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import math
import os  # Importante para o Render

app = Flask(__name__)
app.config['SECRET_KEY'] = 'futebol_maluco_secret'
# cors_allowed_origins="*" é vital para não bloquear conexões no Render
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# --- CONFIGURAÇÕES DO MUNDO ---
WIDTH, HEIGHT = 800, 450
PLAYER_RADIUS = 30
FOOT_RADIUS = 12
BALL_RADIUS = 18

PHASES = ['soccer', 'american', 'basket']

game_state = {
    'players': {
        'p1': {'x': 200, 'y': 350, 'vx': 0, 'vy': 0, 'angle': 0, 'leg_angle': 0, 'score': 0, 'id': None, 'on_ground': False},
        'p2': {'x': 600, 'y': 350, 'vx': 0, 'vy': 0, 'angle': 0, 'leg_angle': 0, 'score': 0, 'id': None, 'on_ground': False}
    },
    'ball': {'x': 400, 'y': 200, 'vx': 0, 'vy': 0},
    'status': 'waiting',
    'winner': None,
    'phase': 'soccer',
    'phase_index': 0
}

inputs = {'p1': False, 'p2': False}
physics_started = False
tick_counter = 0

def reset_positions():
    game_state['ball'] = {'x': 400, 'y': 150, 'vx': 0, 'vy': 0}
    game_state['players']['p1'].update({'x': 200, 'y': 350, 'vx': 0, 'vy': 0, 'angle': 0, 'leg_angle': 0})
    game_state['players']['p2'].update({'x': 600, 'y': 350, 'vx': 0, 'vy': 0, 'angle': 0, 'leg_angle': 0})

def get_phase_params():
    p = game_state['phase']
    if p == 'soccer':
        return {'grav': 0.6, 'jump': -14, 'bounciness': 0.7, 'speed': 6}
    elif p == 'american':
        return {'grav': 0.85, 'jump': -13, 'bounciness': 0.5, 'speed': 8}
    elif p == 'basket':
        return {'grav': 0.5, 'jump': -17, 'bounciness': 0.95, 'speed': 5}
    return {'grav': 0.6, 'jump': -13, 'bounciness': 0.7, 'speed': 5}

def physics_loop():
    global tick_counter
    while True:
        if game_state['status'] in ['playing', 'goal']:
            update_physics()
            tick_counter += 1
        
        socketio.emit('state_update', game_state)
        socketio.sleep(1/60)

def resolve_player_collision(p1, p2):
    dx = p1['x'] - p2['x']
    dy = p1['y'] - p2['y']
    dist = math.sqrt(dx*dx + dy*dy)
    min_dist = PLAYER_RADIUS * 2
    
    if dist < min_dist and dist > 0:
        overlap = (min_dist - dist) / 2
        nx = dx / dist
        ny = dy / dist
        p1['x'] += nx * overlap
        p1['y'] += ny * overlap
        p2['x'] -= nx * overlap
        p2['y'] -= ny * overlap
        tx = p1['vx']
        p1['vx'] = p2['vx'] * 0.8
        p2['vx'] = tx * 0.8

def update_physics():
    params = get_phase_params()
    GRAVITY = params['grav']
    JUMP_FORCE = params['jump']
    MOVE_SPEED = params['speed']
    BOUNCINESS = params['bounciness']

    for pid, p in game_state['players'].items():
        p['vy'] += GRAVITY
        p['y'] += p['vy']
        p['x'] += p['vx']
        p['vx'] *= 0.93
        p['vy'] *= 0.99

        if p['y'] >= HEIGHT - PLAYER_RADIUS:
            p['y'] = HEIGHT - PLAYER_RADIUS
            p['vy'] = 0
            p['on_ground'] = True
        else:
            p['on_ground'] = False

        p['x'] = max(PLAYER_RADIUS, min(WIDTH - PLAYER_RADIUS, p['x']))

        target_angle = 0
        if p['on_ground']:
            sway_speed = 0.15
            sway_amount = 30
            offset = 0 if pid == 'p1' else math.pi 
            target_angle = math.sin(tick_counter * sway_speed + offset) * sway_amount

        if inputs[pid]:
            if p['on_ground']:
                rad = math.radians(p['angle'] - 90) 
                p['vx'] = math.cos(rad) * MOVE_SPEED * 2.0
                p['vy'] = JUMP_FORCE 
                spin_dir = 1 if pid == 'p1' else -1
                p['angle'] += 45 * spin_dir
            
            target_leg = -100 if pid == 'p1' else 100
            inputs[pid] = False
        else:
            target_leg = 0

        p['angle'] = p['angle'] * 0.9 + target_angle * 0.1
        p['leg_angle'] = p['leg_angle'] * 0.8 + target_leg * 0.2

    resolve_player_collision(game_state['players']['p1'], game_state['players']['p2'])

    b = game_state['ball']
    b['vy'] += GRAVITY
    b['x'] += b['vx']
    b['y'] += b['vy']
    b['vx'] *= 0.99

    if b['y'] > HEIGHT - BALL_RADIUS:
        b['y'] = HEIGHT - BALL_RADIUS
        b['vy'] = -b['vy'] * BOUNCINESS
        if abs(b['vy']) < GRAVITY * 2: b['vy'] = 0
    elif b['y'] < BALL_RADIUS:
        b['y'] = BALL_RADIUS
        b['vy'] = abs(b['vy']) * BOUNCINESS

    if b['x'] < 0:
        score_goal('p2')
    elif b['x'] > WIDTH:
        score_goal('p1')

    for pid, p in game_state['players'].items():
        dx, dy = b['x'] - p['x'], b['y'] - p['y']
        dist = math.sqrt(dx**2 + dy**2)
        min_dist = PLAYER_RADIUS + BALL_RADIUS
        
        if dist < min_dist:
            angle = math.atan2(dy, dx)
            force = 1.5
            b['vx'] += math.cos(angle) * force + p['vx']
            b['vy'] += math.sin(angle) * force + p['vy']
            overlap = min_dist - dist
            b['x'] += math.cos(angle) * overlap
            b['y'] += math.sin(angle) * overlap

        foot_orbit = 40
        foot_rad = math.radians(p['angle'] + p['leg_angle'] + 90)
        foot_x = p['x'] + math.cos(foot_rad) * foot_orbit
        foot_y = p['y'] + math.sin(foot_rad) * foot_orbit
        
        fdx, fdy = b['x'] - foot_x, b['y'] - foot_y
        fdist = math.sqrt(fdx**2 + fdy**2)
        
        if fdist < FOOT_RADIUS + BALL_RADIUS:
            fangle = math.atan2(fdy, fdx)
            kick_force = 12
            b['vx'] += math.cos(fangle) * kick_force
            b['vy'] += math.sin(fangle) * kick_force
            foverlap = (FOOT_RADIUS + BALL_RADIUS) - fdist
            b['x'] += math.cos(fangle) * foverlap
            b['y'] += math.sin(fangle) * foverlap

def score_goal(winner):
    game_state['players'][winner]['score'] += 1
    
    if game_state['players'][winner]['score'] >= 10:
        game_state['winner'] = winner
        game_state['status'] = 'game_over'
        socketio.emit('state_update', game_state)
        return

    total_score = game_state['players']['p1']['score'] + game_state['players']['p2']['score']
    if total_score > 0 and total_score % 2 == 0:
        next_idx = (game_state['phase_index'] + 1) % len(PHASES)
        game_state['phase_index'] = next_idx
        game_state['phase'] = PHASES[next_idx]

    game_state['status'] = 'goal'
    socketio.emit('goal_event', {'scorer': winner, 'phase': game_state['phase']})
    socketio.sleep(2)
    reset_positions()
    
    if game_state['status'] != 'game_over':
        game_state['status'] = 'playing'

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    global physics_started
    if not physics_started:
        socketio.start_background_task(physics_loop)
        physics_started = True
    
    sid = request.sid
    if not game_state['players']['p1']['id']:
        game_state['players']['p1']['id'] = sid
        emit('assign_role', {'role': 'p1'})
    elif not game_state['players']['p2']['id']:
        game_state['players']['p2']['id'] = sid
        emit('assign_role', {'role': 'p2'})
    else:
        emit('assign_role', {'role': 'spectator'})

    if game_state['players']['p1']['id'] and game_state['players']['p2']['id']:
        game_state['status'] = 'playing'

@socketio.on('player_input')
def handle_input(data):
    role = data.get('role')
    if role in inputs: inputs[role] = True

@socketio.on('restart_game')
def handle_restart():
    game_state['players']['p1']['score'] = 0
    game_state['players']['p2']['score'] = 0
    game_state['winner'] = None
    game_state['phase'] = 'soccer'
    game_state['phase_index'] = 0
    reset_positions()
    game_state['status'] = 'playing'

@socketio.on('disconnect')
def handle_disconnect():
    for p in game_state['players'].values():
        if p['id'] == request.sid:
            p['id'] = None
            game_state['status'] = 'waiting'

if __name__ == '__main__':
    # Esta parte é só para teste local. No Render, o Gunicorn que manda.
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)
