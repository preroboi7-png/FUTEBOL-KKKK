import eventlet
eventlet.monkey_patch() # Necessário para o Render e Gunicorn

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import threading
import time
import math

app = Flask(__name__)
app.config['SECRET_KEY'] = 'segredo_campeonato_mundial'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# --- CONFIGURAÇÕES FÍSICAS ---
WIDTH, HEIGHT = 800, 450 # Campo um pouco maior
PLAYER_RADIUS = 30
BALL_RADIUS = 18
GRAVITY = 0.6
JUMP_FORCE = -13
MOVE_SPEED = 5
MAX_SCORE = 5

# Estado Global
game_state = {
    'players': {
        'p1': {'x': 150, 'y': 300, 'vx': 0, 'vy': 0, 'angle': 0, 'score': 0, 'id': None},
        'p2': {'x': 650, 'y': 300, 'vx': 0, 'vy': 0, 'angle': 0, 'score': 0, 'id': None}
    },
    'ball': {'x': 400, 'y': 200, 'vx': 0, 'vy': 0},
    'status': 'waiting', # waiting, playing, goal, game_over
    'winner': None
}

# Controle de Inputs
inputs = {'p1': False, 'p2': False}

def reset_positions():
    game_state['ball'] = {'x': WIDTH/2, 'y': HEIGHT/3, 'vx': 0, 'vy': 0}
    game_state['players']['p1'].update({'x': 150, 'y': HEIGHT-100, 'vx': 0, 'vy': 0, 'angle': 0})
    game_state['players']['p2'].update({'x': WIDTH-150, 'y': HEIGHT-100, 'vx': 0, 'vy': 0, 'angle': 0})

def physics_loop():
    while True:
        update_game()
        # Envia update 60 vezes por segundo
        socketio.emit('state_update', game_state)
        eventlet.sleep(1/60)

def update_game():
    if game_state['status'] != 'playing':
        return

    # --- FÍSICA JOGADORES ---
    for pid, p in game_state['players'].items():
        # Gravidade
        p['vy'] += GRAVITY
        p['y'] += p['vy']
        p['x'] += p['vx']
        
        # Atrito aéreo e chão
        p['vx'] *= 0.96
        p['angle'] *= 0.95 # Tenta voltar a ficar em pé

        # Input (O Pulo do Gato - Literalmente)
        if inputs[pid]:
            if p['y'] >= HEIGHT - PLAYER_RADIUS - 15: # Se estiver quase no chão
                p['vy'] = JUMP_FORCE
                # Pula para frente e gira
                direction = 1 if pid == 'p1' else -1
                p['vx'] = MOVE_SPEED * direction
                p['angle'] += 60 * direction # Gira o corpo
            inputs[pid] = False

        # Colisão Chão
        if p['y'] > HEIGHT - PLAYER_RADIUS:
            p['y'] = HEIGHT - PLAYER_RADIUS
            p['vy'] = 0
        
        # Paredes
        p['x'] = max(PLAYER_RADIUS, min(WIDTH - PLAYER_RADIUS, p['x']))

    # --- FÍSICA BOLA ---
    b = game_state['ball']
    b['vy'] += GRAVITY
    b['x'] += b['vx']
    b['y'] += b['vy']
    b['vx'] *= 0.99

    # Colisão Bola-Chão
    if b['y'] > HEIGHT - BALL_RADIUS:
        b['y'] = HEIGHT - BALL_RADIUS
        b['vy'] = -b['vy'] * 0.75 # Quica

    # Colisão Bola-Paredes (Lateral)
    if b['x'] < 0 or b['x'] > WIDTH:
        check_goal(b['x'])
        return # Para a física momentaneamente

    # Colisão Bola-Teto
    if b['y'] < BALL_RADIUS:
        b['y'] = BALL_RADIUS
        b['vy'] = -b['vy']

    # --- COLISÃO JOGADOR x BOLA ---
    for pid, p in game_state['players'].items():
        dx = b['x'] - p['x']
        dy = b['y'] - p['y']
        dist = math.sqrt(dx**2 + dy**2)
        min_dist = PLAYER_RADIUS + BALL_RADIUS

        if dist < min_dist:
            # Vetor de colisão normalizado
            angle = math.atan2(dy, dx)
            force = 12 # Força do chute
            
            # Transfere energia
            b['vx'] += math.cos(angle) * force
            b['vy'] += math.sin(angle) * force
            
            # Empurra jogador levemente
            p['vx'] -= math.cos(angle) * 2
            p['vy'] -= math.sin(angle) * 2

def check_goal(ball_x):
    scorer = 'p2' if ball_x < 0 else 'p1'
    game_state['players'][scorer]['score'] += 1
    game_state['status'] = 'goal'
    
    socketio.emit('goal_event', {'scorer': scorer})
    
    # Verifica vitória
    if game_state['players'][scorer]['score'] >= MAX_SCORE:
        game_state['status'] = 'game_over'
        game_state['winner'] = scorer
        socketio.emit('game_over', {'winner': scorer})
    else:
        # Reseta após 2 segundos
        socketio.sleep(2)
        reset_positions()
        game_state['status'] = 'playing'

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def on_connect():
    print(f"Cliente conectado: {request.sid}")
    # Tenta atribuir um slot vazio
    if game_state['players']['p1']['id'] is None:
        game_state['players']['p1']['id'] = request.sid
        emit('assign_role', {'role': 'p1'})
    elif game_state['players']['p2']['id'] is None:
        game_state['players']['p2']['id'] = request.sid
        emit('assign_role', {'role': 'p2'})
    else:
        emit('assign_role', {'role': 'spectator'})
    
    # Se ambos conectados, inicia
    if game_state['players']['p1']['id'] and game_state['players']['p2']['id']:
        if game_state['status'] == 'waiting':
            game_state['status'] = 'playing'
            reset_positions()

@socketio.on('disconnect')
def on_disconnect():
    # Se um jogador sair, reseta o slot
    for pid in ['p1', 'p2']:
        if game_state['players'][pid]['id'] == request.sid:
            game_state['players'][pid]['id'] = None
            game_state['players'][pid]['score'] = 0
            game_state['status'] = 'waiting'
            socketio.emit('player_left')

@socketio.on('player_input')
def handle_input(data):
    role = data.get('role')
    if role in ['p1', 'p2']:
        inputs[role] = True
        
@socketio.on('restart_game')
def restart():
    game_state['players']['p1']['score'] = 0
    game_state['players']['p2']['score'] = 0
    game_state['status'] = 'playing'
    reset_positions()

if __name__ == '__main__':
    # Inicia a física em background
    eventlet.spawn(physics_loop)
    socketio.run(app, host='0.0.0.0', port=5000)