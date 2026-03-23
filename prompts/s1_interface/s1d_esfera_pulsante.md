# S1-D: Esfera Pulsante (Animação Visual de Estado)

> Prompt auto-contido. Leia e execute.
> Pré-requisito: S1-A, S1-B, S1-C executados
> Arquivos a modificar: `static/index.html` (SOMENTE frontend)

---

## Contexto

O frontend tem status dot (bolinha de 8px com cor) e barra de volume. Funciona, mas é minimalista. Queremos uma **esfera pulsante** central que:
- Mostra visualmente o estado do assistente (escutando, pensando, falando)
- Reage ao volume do mic em tempo real (quando escutando)
- Dá feedback visual claro e intuitivo sem precisar ler texto

---

## Tarefa: Esfera Pulsante com CSS

### Abordagem: CSS puro (sem Canvas)

Usar uma `div` circular com `box-shadow` animado. CSS é mais simples, mais leve, e suficiente pra este efeito. Canvas seria overkill.

### HTML — adicionar entre `.status-bar` e `.chat-container`:

```html
<div class="orb-container" id="orbContainer" style="display:none">
    <div class="orb" id="orb">
        <div class="orb-inner"></div>
    </div>
</div>
```

A esfera fica escondida até o usuário clicar "Iniciar". Após conectar, aparece.

### CSS:

```css
.orb-container {
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 24px 0;
    flex-shrink: 0;
}

.orb {
    width: 80px;
    height: 80px;
    border-radius: 50%;
    position: relative;
    display: flex;
    justify-content: center;
    align-items: center;
    transition: box-shadow 0.3s, transform 0.3s;
}

.orb-inner {
    width: 60px;
    height: 60px;
    border-radius: 50%;
    background: radial-gradient(circle at 35% 35%, #4a4a6a, #2d2d44);
    transition: background 0.3s;
}

/* Estados */
.orb.disconnected {
    box-shadow: 0 0 20px rgba(100, 100, 100, 0.3);
}
.orb.disconnected .orb-inner {
    background: radial-gradient(circle at 35% 35%, #3a3a4a, #2d2d44);
}

.orb.listening {
    box-shadow: 0 0 20px rgba(76, 175, 80, 0.4);
    animation: orb-breathe 3s ease-in-out infinite;
}
.orb.listening .orb-inner {
    background: radial-gradient(circle at 35% 35%, #4caf50, #2d6b30);
}

.orb.thinking {
    box-shadow: 0 0 25px rgba(255, 152, 0, 0.5);
    animation: orb-think 1.2s ease-in-out infinite;
}
.orb.thinking .orb-inner {
    background: radial-gradient(circle at 35% 35%, #ff9800, #b36b00);
}

.orb.speaking {
    box-shadow: 0 0 30px rgba(33, 150, 243, 0.5);
    animation: orb-speak 0.8s ease-in-out infinite;
}
.orb.speaking .orb-inner {
    background: radial-gradient(circle at 35% 35%, #2196f3, #1565c0);
}

/* Animações */
@keyframes orb-breathe {
    0%, 100% { transform: scale(1); box-shadow: 0 0 20px rgba(76, 175, 80, 0.3); }
    50% { transform: scale(1.05); box-shadow: 0 0 35px rgba(76, 175, 80, 0.5); }
}

@keyframes orb-think {
    0%, 100% { transform: scale(1); box-shadow: 0 0 25px rgba(255, 152, 0, 0.4); }
    50% { transform: scale(1.08); box-shadow: 0 0 40px rgba(255, 152, 0, 0.7); }
}

@keyframes orb-speak {
    0%, 100% { transform: scale(1); box-shadow: 0 0 30px rgba(33, 150, 243, 0.4); }
    50% { transform: scale(1.1); box-shadow: 0 0 45px rgba(33, 150, 243, 0.7); }
}

/* Reação ao volume do mic (classes dinâmicas) */
.orb.listening.vol-low { transform: scale(1.02); }
.orb.listening.vol-mid { transform: scale(1.08); }
.orb.listening.vol-high { transform: scale(1.15); box-shadow: 0 0 50px rgba(76, 175, 80, 0.7); }

@media (max-width: 600px) {
    .orb { width: 60px; height: 60px; }
    .orb-inner { width: 45px; height: 45px; }
    .orb-container { padding: 16px 0; }
}
```

### JavaScript:

1. **Mostrar/esconder a esfera:**
   - Em `start()` (quando conecta): `document.getElementById('orbContainer').style.display = 'flex';`
   - Em `disconnect()`: `document.getElementById('orbContainer').style.display = 'none';`

2. **Atualizar estado da esfera em `handleStatus()`:**
   ```javascript
   const orb = document.getElementById('orb');
   orb.className = 'orb ' + status;
   ```

   Mapear os status do server pra classes CSS:
   - `listening` → `.orb.listening` (verde, respiração lenta)
   - `thinking` → `.orb.thinking` (laranja, pulso médio)
   - `speaking` → `.orb.speaking` (azul, pulso rápido)
   - default → `.orb.disconnected` (cinza)

3. **Reação ao volume do mic em `processAudioChunk()`:**
   
   Após calcular RMS e `pct`, ANTES do check `if (isMuted)`:
   ```javascript
   // Atualizar esfera com volume (só no estado listening)
   const orb = document.getElementById('orb');
   if (orb.classList.contains('listening') && !isMuted) {
       orb.classList.remove('vol-low', 'vol-mid', 'vol-high');
       if (pct > 60) orb.classList.add('vol-high');
       else if (pct > 25) orb.classList.add('vol-mid');
       else if (pct > 5) orb.classList.add('vol-low');
   }
   ```

   E quando mutado ou não-listening, remover as classes de volume:
   ```javascript
   if (isMuted) {
       orb.classList.remove('vol-low', 'vol-mid', 'vol-high');
       // ... resto do mute handling
   }
   ```

4. **Na função `setStatus()`**, adicionar sync da esfera:
   ```javascript
   function setStatus(cls, text) {
       statusDot.className = 'status-dot ' + cls;
       statusText.textContent = text;
       // Sync orb (se existir)
       const orb = document.getElementById('orb');
       if (orb) {
           orb.className = 'orb ' + cls;
       }
   }
   ```

   **Nota:** usar a MESMA classe no statusDot e no orb simplifica tudo. Os nomes de classe já são iguais: `listening`, `thinking`, `speaking`, `disconnected`, `connected`.

   Verificar que `connected` e `listening` usem a mesma animação na esfera (verde, respiração) — pois `connected` é o estado entre conexão e primeira fala.

---

## Tamanho e posicionamento

A esfera fica entre o header (status-bar) e o chat. É compacta (80px desktop, 60px mobile). Se o chat tiver muitas mensagens, a esfera não se move — o chat scrolla embaixo dela.

Se tu achar que a esfera ocupa espaço demais, uma alternativa futura é colocá-la DENTRO da bottom-bar substituindo a barra de volume. Mas por agora, separado é mais simples.

---

## O que NÃO fazer

- NÃO remover a barra de volume existente (mantém como complemento)
- NÃO remover o status dot no header (mantém como informação de texto)
- NÃO usar Canvas ou bibliotecas externas — CSS puro
- NÃO mexer em `server_ws.py` ou `core/`
- NÃO mudar a lógica de VAD ou barge-in
- NÃO fazer a esfera clicável (não é botão, é feedback visual)

---

## Critério de sucesso

1. [ ] Esfera aparece após clicar "Iniciar"
2. [ ] Esfera verde com respiração lenta quando escutando
3. [ ] Esfera reage ao volume do mic (cresce quando fala, diminui em silêncio)
4. [ ] Esfera laranja pulsando quando pensando
5. [ ] Esfera azul pulsando quando falando
6. [ ] Esfera some ao desconectar
7. [ ] Esfera cinza e estática quando muted (sem reação ao volume)
8. [ ] Responsivo: menor em mobile (<600px)
9. [ ] `python -m pytest tests/ -v` — todos os testes passam

---

## Teste manual

1. Iniciar → esfera aparece verde, respirando
2. Falar → esfera cresce com volume
3. Parar de falar → esfera volta ao tamanho normal
4. Esperando resposta → esfera fica laranja, pulsa
5. Resposta tocando → esfera fica azul
6. Mutar → esfera não reage ao som
7. Desconectar → esfera some
8. Testar em tela pequena (F12 → responsive mode)
