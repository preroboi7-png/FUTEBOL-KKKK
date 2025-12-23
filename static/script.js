const socket = io();
const canvas = document.getElementById('gameCanvas');
const ctx = canvas.getContext('2d');

let myRole = 'spectator';
let particles = []; // Confetes

// Estado Local para renderização (Suavização)
let renderState = {
    p1: {x: 150, y: 300, angle: 0},
    p2: {x: 650, y: 300, angle: 0},
    ball: {x: 400, y: 200}
};

// Estado Alvo (o que veio do servidor)
let targetState = null;

// --- SOCKET EVENTS ---

socket.on('assign_role', (data) => {
    myRole = data.role;
    let roleName = myRole === 'p1' ? 'JOGADOR 1 (AZUL)' : (myRole === 'p2' ? 'JOGADOR 2 (VERMELHO)' : 'ESPECTADOR');
    document.getElementById('my-role-display').innerText = roleName;
    
    // Esconde o overlay se o jogo começar
    if(myRole !== 'spectator') document.getElementById('msg-overlay').style.display = 'none';
});

socket.on('state_update', (serverState) => {
    targetState = serverState;
    
    // Atualiza placar
    document.getElementById('score-p1').innerText = serverState.players.p1.score;
    document.getElementById('score-p2').innerText = serverState.players.p2.score;

    // Gerencia mensagens
    const overlay = document.getElementById('msg-overlay');
    const msgText = document.getElementById('msg-text');
    const restartBtn = document.getElementById('restart-btn');

    if (serverState.status === 'waiting') {
        overlay.style.display = 'flex';
        msgText.innerText = "Aguardando Oponente...";
        restartBtn.style.display = 'none';
    } else if (serverState.status === 'game_over') {
        overlay.style.display = 'flex';
        let winnerName = serverState.winner === 'p1' ? 'AZUL' : 'VERMELHO';
        msgText.innerText = `${winnerName} VENCEU!`;
        if(myRole !== 'spectator') restartBtn.style.display = 'block';
    } else if (serverState.status === 'goal') {
        overlay.style.display = 'flex';
        msgText.innerText = "GOL!!!";
        restartBtn.style.display = 'none';
        // Some depois de um tempo via CSS ou lógica, mas o servidor vai mudar status logo
    } else {
        overlay.style.display = 'none';
    }
});

socket.on('goal_event', (data) => {
    createExplosion(data.scorer === 'p1' ? WIDTH : 0, HEIGHT/2, data.scorer === 'p1' ? '#4facfe' : '#ff6b6b');
});

// --- INPUTS ---
function sendInput() {
    if (myRole === 'p1' || myRole === 'p2') {
        socket.emit('player_input', { role: myRole });
    }
}
window.addEventListener('keydown', (e) => {
    if (e.code === 'Space' || e.code === 'ArrowUp' || e.code === 'KeyW' || e.code === 'Enter') {
        sendInput();
    }
});
window.addEventListener('touchstart', (e) => {
    e.preventDefault(); // Evita scroll
    sendInput();
}, {passive: false});
window.addEventListener('mousedown', sendInput);

function requestRestart() {
    socket.emit('restart_game');
}

// --- RENDERIZAÇÃO E INTERPOLAÇÃO ---

// Função LERP (Linear Interpolation) para suavizar
function lerp(start, end, t) {
    return start * (1 - t) + end * t;
}

function gameLoop() {
    // Fator de suavização (0.1 = lento/suave, 0.5 = rápido)
    const smooth = 0.2; 

    if (targetState) {
        // Suaviza P1
        renderState.p1.x = lerp(renderState.p1.x, targetState.players.p1.x, smooth);
        renderState.p1.y = lerp(renderState.p1.y, targetState.players.p1.y, smooth);
        renderState.p1.angle = lerp(renderState.p1.angle, targetState.players.p1.angle, smooth);

        // Suaviza P2
        renderState.p2.x = lerp(renderState.p2.x, targetState.players.p2.x, smooth);
        renderState.p2.y = lerp(renderState.p2.y, targetState.players.p2.y, smooth);
        renderState.p2.angle = lerp(renderState.p2.angle, targetState.players.p2.angle, smooth);

        // Suaviza Bola
        renderState.ball.x = lerp(renderState.ball.x, targetState.ball.x, smooth);
        renderState.ball.y = lerp(renderState.ball.y, targetState.ball.y, smooth);
    }

    draw();
    requestAnimationFrame(gameLoop);
}

const WIDTH = 800;
const HEIGHT = 450;

function draw() {
    ctx.clearRect(0, 0, WIDTH, HEIGHT);

    // Gols
    ctx.fillStyle = 'rgba(255,255,255,0.3)';
    ctx.fillRect(0, HEIGHT-140, 50, 140); // Esquerda
    ctx.fillRect(WIDTH-50, HEIGHT-140, 50, 140); // Direita

    // Jogadores
    drawPlayer(renderState.p1, '#4facfe', true);
    drawPlayer(renderState.p2, '#ff6b6b', false);

    // Bola
    drawBall(renderState.ball);

    // Partículas (Confete)
    updateParticles();
}

function drawPlayer(p, color, isLeft) {
    ctx.save();
    ctx.translate(p.x, p.y);
    ctx.rotate((p.angle * Math.PI) / 180);

    // Corpo
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.roundRect(-25, -35, 50, 70, 10);
    ctx.fill();
    
    // Borda preta
    ctx.strokeStyle = '#000';
    ctx.lineWidth = 3;
    ctx.stroke();

    // Rosto
    ctx.fillStyle = '#ffccaa';
    ctx.beginPath();
    ctx.arc(0, -45, 20, 0, Math.PI*2);
    ctx.fill();
    ctx.stroke();

    // Olhos
    ctx.fillStyle = '#fff';
    ctx.beginPath();
    let eyeOff = isLeft ? 6 : -6;
    ctx.arc(eyeOff, -45, 6, 0, Math.PI*2);
    ctx.fill();
    ctx.fillStyle = '#000';
    ctx.beginPath();
    ctx.arc(eyeOff + (isLeft?2:-2), -45, 2, 0, Math.PI*2);
    ctx.fill();

    ctx.restore();
}

function drawBall(b) {
    ctx.save();
    ctx.translate(b.x, b.y);
    ctx.beginPath();
    ctx.arc(0, 0, 18, 0, Math.PI*2);
    ctx.fillStyle = '#fff';
    ctx.fill();
    ctx.strokeStyle = '#000';
    ctx.lineWidth = 3;
    ctx.stroke();
    
    // Detalhe bola (pentágono simulado)
    ctx.beginPath();
    ctx.moveTo(0, -18);
    ctx.lineTo(0, 18);
    ctx.moveTo(-18, 0);
    ctx.lineTo(18, 0);
    ctx.stroke();
    ctx.restore();
}

// --- SISTEMA DE PARTÍCULAS (CONFETE) ---
function createExplosion(x, y, color) {
    for(let i=0; i<50; i++) {
        particles.push({
            x: x, y: y,
            vx: (Math.random() - 0.5) * 15,
            vy: (Math.random() - 0.5) * 15,
            life: 1.0,
            color: color
        });
    }
}

function updateParticles() {
    for(let i=particles.length-1; i>=0; i--) {
        let p = particles[i];
        p.x += p.vx;
        p.y += p.vy;
        p.life -= 0.02;
        p.vy += 0.5; // Gravidade confete

        ctx.globalAlpha = p.life;
        ctx.fillStyle = p.color;
        ctx.fillRect(p.x, p.y, 8, 8);
        ctx.globalAlpha = 1.0;

        if(p.life <= 0) particles.splice(i, 1);
    }
}

// Inicia o loop visual
requestAnimationFrame(gameLoop);