import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import math
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'futebol_maluco_secret'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# --- CONFIGURAÇÕES GERAIS ---
WIDTH, HEIGHT = 800, 450
PLAYER_RADIUS = 30
FOOT_RADIUS = 12
BALL_RADIUS = 18

# Fases do jogo
PHASES = ['soccer', 'american', 'basket']

# Estado Global do Jogo
game_state = {
    'players': {
        'p1': {'x': 200, 'y': 350, 'vx': 0, 'vy': 0, 'angle': 0, 'leg_angle': 0, 'score': 0, 'id': None, 'on_ground': False},
        'p2': {'x': 600, 'y': 350, 'vx': 0, 'vy': 0, 'angle': 0, 'leg_angle': 0, 'score': 0, 'id': None, 'on_ground': False}
    },
    'ball': {'x': 400, 'y': 200, 'vx': 0, 'vy': 0},
    'status': 'waiting', # waiting, playing, goal, game_over
    'winner': None,
    'phase': 'soccer', # soccer, american, basket
    'phase_index': 0
}

inputs = {'p1': False, 'p2': False}
physics_started = False
tick_counter = 0

def reset_positions():
    # Reinicia posições mas mantém pontuação e fase
    game_state['ball'] = {'x': 400, 'y': 150, 'vx': 0, 'vy': 0}
    game_state['players']['p1'].update({'x': 200, 'y': 350, 'vx': 0, 'vy': 0, 'angle': 0, 'leg_angle': 0})
    game_state['players']['p2'].update({'x': 600, 'y': 350, 'vx': 0, 'vy': 0, 'angle': 0, 'leg_angle': 0})

def get_phase_params():
    p = game_state['phase']
    if p == 'soccer':
        return {'grav': 0.6, 'jump': -14, 'bounciness': 0.7, 'speed': 6}
    elif p == 'american':
        return {'grav': 0.8, 'jump': -12, 'bounciness': 0.5, 'speed': 8} # Bola pesada, jogo rápido
    elif p == 'basket':
        return {'grav': 0.5, 'jump': -16, 'bounciness': 0.95, 'speed': 5} # Bola quica muito, pulo alto
    return {'grav': 0.6, 'jump': -13, 'bounciness': 0.7, 'speed': 5}

def physics_loop():
    global tick_counter
    while True:
        if game_state['status'] == 'playing' or game_state['status'] == 'goal':
            update_physics()
            tick_counter += 1
        
        socketio.emit('state_update', game_state)
        socketio.sleep(1/60)

def resolve_collision_circles(x1, y1, r1, x2, y2, r2):
    dx = x1 - x2
    dy = y1 - y2
    dist = math.sqrt(dx*dx + dy*dy)
    if dist < r1 + r2 and dist > 0:
        overlap = (r1 + r2) - dist
        nx = dx / dist
        ny = dy / dist
        return nx * overlap, ny * overlap
    return 0, 0

def update_physics():
    params = get_phase_params()
    GRAVITY = params['grav']
    JUMP_FORCE = params['jump']
    MOVE_SPEED = params['speed']
    BOUNCINESS = params['bounciness']

    # --- JOGADORES ---
    for pid, p in game_state['players'].items():
        # Aplica gravidade
        p['vy'] += GRAVITY
        p['y'] += p['vy']
        p['x'] += p['vx']
        
        # Atrito chão/ar
        p['vx'] *= 0.92
        p['vy'] *= 0.98

        # Chão
        if p['y'] >= HEIGHT - PLAYER_RADIUS:
            p['y'] = HEIGHT - PLAYER_RADIUS
            p['vy'] = 0
            p['on_ground'] = True
        else:
            p['on_ground'] = False

        # Paredes laterais (Jogadores)
        p['x'] = max(PLAYER_RADIUS, min(WIDTH - PLAYER_RADIUS, p['x']))

        # BALANÇO (Sway)
        # Se estiver no chão, balança de um lado para o outro
        target_angle = 0
        if p['on_ground']:
            # P1 balança invertido ao P2 para simular espelho ou mesma direção, dependendo da preferência
            sway_speed = 0.1
            sway_amount = 25 # Graus
            direction_mod = 1 if pid == 'p1' else -1
            
            # Cria oscilação senoidal
            oscillation = math.sin(tick_counter * sway_speed) 
            target_angle = oscillation * sway_amount * direction_mod

        # INPUT (Pulo / Chute)
        if inputs[pid]:
            if p['on_ground']:
                # Pula na direção do ângulo atual (cabeçada/impulso)
                rad = math.radians(p['angle'] - 90) # -90 porque 0 é direita
                p['vx'] = math.cos(rad) * MOVE_SPEED * 2.5 # Impulso horizontal
                p['vy'] = JUMP_FORCE # Impulso vertical fixo forte
                
                # Rotaciona para chutar
                p['angle'] += 45 if pid == 'p1' else -45
            
            # Chute (Levanta o pé)
            target_leg = -90 if pid == 'p1' else 90 # Perna vai para frente
            inputs[pid] = False # Consome o input
        else:
            # Perna volta ao normal
            target_leg = 0

        # Suaviza rotação do corpo e da perna
        p['angle'] = p['angle'] * 0.9 + target_angle * 0.1
        p['leg_angle'] = p['leg_angle'] * 0.8 + target_leg * 0.2

    # --- COLISÃO ENTRE JOGADORES (Não atravessar) ---
    p1 = game_state['players']['p1']
    p2 = game_state['players']['p2']
    p_dx, p_dy = resolve_collision_circles(p1['x'], p1['y'], PLAYER_RADIUS, p2['x'], p2['y'], PLAYER_RADIUS)
    if p_dx != 0:
        # Empurra cada um metade do overlap
        p1['x'] += p_dx * 0.5
        p1['y'] += p_dy * 0.5
        p2['x'] -= p_dx * 0.5
        p2['y'] -= p_dy * 0.5
        # Troca um pouco de momento (choque elástico simples)
        temp_vx = p1['vx']
        p1['vx'] = p2['vx'] * 0.5
        p2['vx'] = temp_vx * 0.5

    # --- BOLA ---
    b = game_state['ball']
    b['vy'] += GRAVITY
    b['x'] += b['vx']
    b['y'] += b['vy']
    b['vx'] *= 0.99 # Atrito ar

    # Colisão Bola com Chão/Teto
    if b['y'] > HEIGHT - BALL_RADIUS:
        b['y'] = HEIGHT - BALL_RADIUS
        b['vy'] = -b['vy'] * BOUNCINESS
        # Se a velocidade for muito baixa, para de quicar (evita vibração)
        if abs(b['vy']) < GRAVITY * 2: b['vy'] = 0
            
    elif b['y'] < BALL_RADIUS:
        b['y'] = BALL_RADIUS
        b['vy'] = abs(b['vy']) * BOUNCINESS

    # Colisão Bola com Paredes (GOL Lógica Básica antes de marcar)
    if b['x'] < 0:
        score_goal('p2')
    elif b['x'] > WIDTH:
        score_goal('p1')

    # --- COLISÃO JOGADOR-BOLA (CORPO E PÉ) ---
    for pid, p in game_state['players'].items():
        # 1. Colisão com o CORPO
        dx, dy = b['x'] - p['x'], b['y'] - p['y']
        dist = math.sqrt(dx**2 + dy**2)
        min_dist = PLAYER_RADIUS + BALL_RADIUS
        
        if dist < min_dist:
            angle = math.atan2(dy, dx)
            force = 12 # Força de repulsão do corpo
            b['vx'] += math.cos(angle) * 2
            b['vy'] += math.sin(angle) * 2
            # Ajusta posição para não grudar
            overlap = min_dist - dist
            b['x'] += math.cos(angle) * overlap
            b['y'] += math.sin(angle) * overlap
            # Transfere velocidade do player para bola
            b['vx'] += p['vx'] * 1.5
            b['vy'] += p['vy'] * 1.5

        # 2. Colisão com o PÉ (Simulado como um círculo menor orbitando o corpo)
        # Calcula posição do pé baseada no ângulo do corpo + ângulo da perna
        foot_orbit = 40 # Distancia do centro do corpo
        foot_rad_angle = math.radians(p['angle'] + p['leg_angle'] + 90) # +90 para apontar pra baixo/frente
        foot_x = p['x'] + math.cos(foot_rad_angle) * foot_orbit
        foot_y = p['y'] + math.sin(foot_rad_angle) * foot_orbit
        
        fdx, fdy = b['x'] - foot_x, b['y'] - foot_y
        fdist = math.sqrt(fdx**2 + fdy**2)
        
        if fdist < FOOT_RADIUS + BALL_RADIUS:
            fangle = math.atan2(fdy, fdx)
            # O Chute é mais forte que o corpo
            kick_power = 1.5 if inputs[pid] else 1.0 # Se tiver apertando botão, chuta mais forte
            b['vx'] += math.cos(fangle) * 15 * kick_power
            b['vy'] += math.sin(fangle) * 15 * kick_power
            # Ajusta posição
            foverlap = (FOOT_RADIUS + BALL_RADIUS) - fdist
            b['x'] += math.cos(fangle) * foverlap
            b['y'] += math.sin(fangle) * foverlap

def score_goal(winner):
    game_state['players'][winner]['score'] += 1
    game_state['status'] = 'goal'
    
    # Verifica Vitória
    if game_state['players'][winner]['score'] >= 10:
        game_state['winner'] = winner
        game_state['status'] = 'game_over'
        socketio.emit('state_update', game_state)
        return

    # Troca de Fase a cada 2 gols (somando placar total)
    total_score = game_state['players']['p1']['score'] + game_state['players']['p2']['score']
    if total_score > 0 and total_score % 2 == 0:
        next_idx = (game_state['phase_index'] + 1) % len(PHASES)
        game_state['phase_index'] = next_idx
        game_state['phase'] = PHASES[next_idx]

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
    # Zera tudo
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
            # Resetar jogo se alguém sair? Por enquanto apenas pausa.

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)
