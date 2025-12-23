const socket = io();
const canvas = document.getElementById('gameCanvas');
const ctx = canvas.getContext('2d');

let myRole = 'spectator';
let particles = [];
let currentPhase = 'soccer'; 

const WIDTH = 800;
const HEIGHT = 450;

let renderState = {
    p1: {x: 200, y: 350, angle: 0, leg_angle: 0},
    p2: {x: 600, y: 350, angle: 0, leg_angle: 0},
    ball: {x: 400, y: 200}
};

let targetState = null;

socket.on('assign_role', (data) => {
    myRole = data.role;
    let roleName = myRole === 'p1' ? 'JOGADOR 1 (AZUL)' : (myRole === 'p2' ? 'JOGADOR 2 (VERMELHO)' : 'ESPECTADOR');
    document.getElementById('my-role-display').innerText = roleName;
    if(myRole !== 'spectator') document.getElementById('msg-overlay').style.display = 'none';
});

socket.on('state_update', (serverState) => {
    targetState = serverState;
    currentPhase = serverState.phase;
    
    updatePhaseText();

    document.getElementById('score-p1').innerText = serverState.players.p1.score;
    document.getElementById('score-p2').innerText = serverState.players.p2.score;

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
    } else {
        overlay.style.display = 'none';
    }
});

socket.on('goal_event', (data) => {
    createExplosion(data.scorer === 'p1' ? WIDTH : 0, HEIGHT/2, data.scorer === 'p1' ? '#4facfe' : '#ff6b6b');
});

function updatePhaseText() {
    const timerDiv = document.querySelector('.timer');
    if(currentPhase === 'soccer') timerDiv.innerText = "⚽ FUTEBOL (10 PTS)";
    else if(currentPhase === 'american') timerDiv.innerText = "🏈 FUTEBOL AMERICANO";
    else if(currentPhase === 'basket') timerDiv.innerText = "🏀 BASQUETE";
}

function sendInput() {
    if (myRole === 'p1' || myRole === 'p2') {
        socket.emit('player_input', { role: myRole });
    }
}
window.addEventListener('keydown', (e) => {
    if (['Space', 'ArrowUp', 'KeyW', 'Enter'].includes(e.code)) sendInput();
});
window.addEventListener('touchstart', (e) => {
    e.preventDefault(); 
    sendInput();
}, {passive: false});
window.addEventListener('mousedown', sendInput);

function requestRestart() {
    socket.emit('restart_game');
}

function lerp(start, end, t) {
    return start * (1 - t) + end * t;
}

function gameLoop() {
    const smooth = 0.25; 

    if (targetState) {
        ['p1', 'p2'].forEach(pid => {
            renderState[pid].x = lerp(renderState[pid].x, targetState.players[pid].x, smooth);
            renderState[pid].y = lerp(renderState[pid].y, targetState.players[pid].y, smooth);
            renderState[pid].angle = lerp(renderState[pid].angle, targetState.players[pid].angle, smooth);
            renderState[pid].leg_angle = lerp(renderState[pid].leg_angle, targetState.players[pid].leg_angle, smooth);
        });

        renderState.ball.x = lerp(renderState.ball.x, targetState.ball.x, smooth);
        renderState.ball.y = lerp(renderState.ball.y, targetState.ball.y, smooth);
    }
    draw();
    requestAnimationFrame(gameLoop);
}

function draw() {
    ctx.clearRect(0, 0, WIDTH, HEIGHT);
    drawBackground();
    drawGoals();
    drawPlayer(renderState.p1, '#4facfe', true);
    drawPlayer(renderState.p2, '#ff6b6b', false);
    drawBall(renderState.ball);
    updateParticles();
}

function drawBackground() {
    if (currentPhase === 'basket') {
        ctx.fillStyle = '#e67e22'; 
        ctx.fillRect(0,0,WIDTH,HEIGHT);
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(WIDTH/2, 0); ctx.lineTo(WIDTH/2, HEIGHT); ctx.stroke();
        ctx.beginPath(); ctx.arc(WIDTH/2, HEIGHT/2, 50, 0, Math.PI*2); ctx.stroke();
    }
}

function drawGoals() {
    ctx.fillStyle = 'rgba(255,255,255,0.3)';
    if (currentPhase === 'basket') {
        ctx.fillStyle = '#c0392b';
        ctx.fillRect(0, HEIGHT-250, 10, 250); 
        ctx.fillRect(0, HEIGHT-250, 60, 5);   
        ctx.fillRect(WIDTH-10, HEIGHT-250, 10, 250); 
        ctx.fillRect(WIDTH-60, HEIGHT-250, 60, 5);   
    } else if (currentPhase === 'american') {
        ctx.fillStyle = '#f1c40f';
        ctx.fillRect(0, HEIGHT-200, 10, 200);
        ctx.fillRect(WIDTH-10, HEIGHT-200, 10, 200);
    } else {
        ctx.fillStyle = 'rgba(255,255,255,0.5)';
        ctx.fillRect(0, HEIGHT-140, 50, 140);
        ctx.fillRect(WIDTH-50, HEIGHT-140, 50, 140);
    }
}

function drawPlayer(p, color, isLeft) {
    ctx.save();
    ctx.translate(p.x, p.y);
    ctx.rotate((p.angle * Math.PI) / 180);

    ctx.save();
    ctx.rotate(((p.leg_angle) * Math.PI) / 180); 
    ctx.fillStyle = '#333';
    ctx.beginPath();
    ctx.roundRect(-8, 10, 16, 40, 5);
    ctx.fill();
    ctx.beginPath();
    let footDir = isLeft ? 1 : -1;
    ctx.ellipse(footDir * 5, 50, 12, 8, 0, 0, Math.PI*2); 
    ctx.fill();
    ctx.restore();

    ctx.fillStyle = color;
    ctx.beginPath(); ctx.arc(0, 0, 30, 0, Math.PI*2); ctx.fill();
    ctx.strokeStyle = '#000'; ctx.lineWidth = 3; ctx.stroke();

    ctx.fillStyle = '#ffccaa';
    ctx.beginPath(); ctx.arc(0, -10, 15, 0, Math.PI*2);
    
    ctx.fillStyle = '#fff';
    ctx.beginPath();
    let eyeOff = isLeft ? 10 : -10;
    ctx.arc(eyeOff, -5, 8, 0, Math.PI*2); ctx.fill();
    ctx.fillStyle = '#000';
    ctx.beginPath(); ctx.arc(eyeOff + (isLeft?3:-3), -5, 3, 0, Math.PI*2); ctx.fill();
    ctx.restore();
}

function drawBall(b) {
    ctx.save();
    ctx.translate(b.x, b.y);
    if (currentPhase === 'american') {
        ctx.scale(1.3, 0.8);
        ctx.fillStyle = '#8B4513';
        ctx.beginPath(); ctx.arc(0, 0, 18, 0, Math.PI*2); ctx.fill();
        ctx.strokeStyle = '#fff'; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(-15,0); ctx.lineTo(15,0); ctx.stroke();
    } else if (currentPhase === 'basket') {
        ctx.fillStyle = '#e67e22';
        ctx.beginPath(); ctx.arc(0, 0, 20, 0, Math.PI*2); ctx.fill();
        ctx.strokeStyle = '#000'; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(-20,0); ctx.lineTo(20,0); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(0,-20); ctx.lineTo(0,20); ctx.stroke();
    } else {
        ctx.beginPath(); ctx.arc(0, 0, 18, 0, Math.PI*2);
        ctx.fillStyle = '#fff'; ctx.fill();
        ctx.strokeStyle = '#000'; ctx.lineWidth = 3; ctx.stroke();
        ctx.beginPath(); ctx.moveTo(0, -18); ctx.lineTo(0, 18); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(-18, 0); ctx.lineTo(18, 0); ctx.stroke();
    }
    ctx.restore();
}

function createExplosion(x, y, color) {
    for(let i=0; i<50; i++) {
        particles.push({
            x: x, y: y,
            vx: (Math.random() - 0.5) * 20,
            vy: (Math.random() - 0.5) * 20,
            life: 1.0,
            color: color
        });
    }
}

function updateParticles() {
    for(let i=particles.length-1; i>=0; i--) {
        let p = particles[i];
        p.x += p.vx; p.y += p.vy; p.life -= 0.02; p.vy += 0.5;
        ctx.globalAlpha = p.life; ctx.fillStyle = p.color;
        ctx.fillRect(p.x, p.y, 8, 8);
        ctx.globalAlpha = 1.0;
        if(p.life <= 0) particles.splice(i, 1);
    }
}

requestAnimationFrame(gameLoop);
