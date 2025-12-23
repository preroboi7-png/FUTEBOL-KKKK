import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import math

app = Flask(__name__)
app.config['SECRET_KEY'] = 'futebol_kkkk_secret'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# --- CONFIGURAÇÕES ---
WIDTH, HEIGHT = 800, 450
PLAYER_RADIUS = 30
BALL_RADIUS = 18
GRAVITY = 0.6
JUMP_FORCE = -13
MOVE_SPEED = 5

game_state = {
    'players': {
        'p1': {'x': 150, 'y': 350, 'vx': 0, 'vy': 0, 'angle': 0, 'score': 0, 'id': None},
        'p2': {'x': 650, 'y': 350, 'vx': 0, 'vy': 0, 'angle': 0, 'score': 0, 'id': None}
    },
    'ball': {'x': 400, 'y': 200, 'vx': 0, 'vy': 0},
    'status': 'waiting',
    'winner': None
}

inputs = {'p1': False, 'p2': False}
physics_started = False

def reset_positions():
    game_state['ball'] = {'x': 400, 'y': 150, 'vx': 0, 'vy': 0}
    game_state['players']['p1'].update({'x': 150, 'y': 350, 'vx': 0, 'vy': 0, 'angle': 0})
    game_state['players']['p2'].update({'x': 650, 'y': 350, 'vx': 0, 'vy': 0, 'angle': 0})

def physics_loop():
    while True:
        if game_state['status'] == 'playing' or game_state['status'] == 'goal':
            update_physics()
        socketio.emit('state_update', game_state)
        socketio.sleep(1/60)

def update_physics():
    # Jogadores
    for pid, p in game_state['players'].items():
        p['vy'] += GRAVITY
        p['y'] += p['vy']
        p['x'] += p['vx']
        p['vx'] *= 0.95
        p['angle'] *= 0.94

        if inputs[pid]:
            if p['y'] >= HEIGHT - PLAYER_RADIUS - 10:
                p['vy'] = JUMP_FORCE
                direction = 1 if pid == 'p1' else -1
                p['vx'] = MOVE_SPEED * direction
                p['angle'] = 45 * direction
            inputs[pid] = False

        if p['y'] > HEIGHT - PLAYER_RADIUS:
            p['y'] = HEIGHT - PLAYER_RADIUS
            p['vy'] = 0
        p['x'] = max(PLAYER_RADIUS, min(WIDTH - PLAYER_RADIUS, p['x']))

    # Bola
    b = game_state['ball']
    b['vy'] += GRAVITY
    b['x'] += b['vx']
    b['y'] += b['vy']
    b['vx'] *= 0.99

    if b['y'] > HEIGHT - BALL_RADIUS:
        b['y'] = HEIGHT - BALL_RADIUS
        b['vy'] = -b['vy'] * 0.7
    
    if b['y'] < BALL_RADIUS:
        b['y'] = BALL_RADIUS
        b['vy'] *= -0.7

    # Gols e Colisões
    if b['x'] < 0:
        score_goal('p2')
    elif b['x'] > WIDTH:
        score_goal('p1')

    # Colisão Jogador-Bola
    for pid, p in game_state['players'].items():
        dx, dy = b['x'] - p['x'], b['y'] - p['y']
        dist = math.sqrt(dx**2 + dy**2)
        if dist < PLAYER_RADIUS + BALL_RADIUS:
            angle = math.atan2(dy, dx)
            b['vx'] = math.cos(angle) * 15
            b['vy'] = math.sin(angle) * 15

def score_goal(winner):
    game_state['players'][winner]['score'] += 1
    game_state['status'] = 'goal'
    socketio.emit('goal_event', {'scorer': winner})
    socketio.sleep(2)
    reset_positions()
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

@socketio.on('disconnect')
def handle_disconnect():
    for p in game_state['players'].values():
        if p['id'] == request.sid:
            p['id'] = None
            game_state['status'] = 'waiting'

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)
