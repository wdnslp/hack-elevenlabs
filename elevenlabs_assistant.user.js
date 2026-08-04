// ==UserScript==
// @name         ElevenLabs Assistant
// @namespace    http://tampermonkey.net/
// @version      2.3
// @description  ElevenLabs TTS Assistant with Smart 2-Stage Limit Detector (Cookie Clear -> Auto-VPN IP Switcher)
// @match        https://elevenlabs.io/*
// @grant        none
// @run-at       document-start
// ==/UserScript==

(function() {
    'use strict';

    let currentChunkIdx = 0;
    let chunks = [];
    let isAutoPlay = true;
    let lastCapturedBlob = null;
    let downloadedSizes = new Set();
    let isLimitClearedRecently = false;

    // IP Switch State Tracking
    let hasClearedCookiesForCurrentIP = false;

    // MediaSource buffer accumulator
    let mediaSourceChunks = [];
    let mediaSourceTimer = null;
    let isFetchStreamHandled = false;

    // --- 0. ON-SCREEN DEBUG LOGGER ---
    function log(msg, color) {
        console.log('[ElevenLabs Assistant]', msg);
        const logBox = document.getElementById('el-debug-log');
        if (logBox) {
            const item = document.createElement('div');
            item.style.color = color || '#38bdf8';
            item.style.marginBottom = '2px';
            item.textContent = '[' + new Date().toLocaleTimeString() + '] ' + msg;
            logBox.appendChild(item);
            logBox.scrollTop = logBox.scrollHeight;
        }
    }

    function showStatus(msg, color) {
        const bar = document.getElementById('el-status-bar');
        if (bar) {
            bar.textContent = msg;
            bar.style.color = color || '#94a3b8';
        }
    }

    // --- 1. COOKIE AND SITE STORAGE AUTO-CLEANER ---
    function clearSiteData() {
        try {
            window.localStorage.clear();
            window.sessionStorage.clear();
            document.cookie.split(";").forEach(function(c) {
                document.cookie = c.replace(/^ +/, "").replace(/=.*/, "=;expires=" + new Date().toUTCString() + ";path=/;domain=" + window.location.hostname);
                document.cookie = c.replace(/^ +/, "").replace(/=.*/, "=;expires=" + new Date().toUTCString() + ";path=/");
            });
            log('🧹 АВТО-ОЧИСТКА: Куки, LocalStorage и сессии ElevenLabs сброшены!', '#f59e0b');
            showStatus('🚨 Лимит! Куки очищены. Если окно появится снова — требуется смена IP в VPN.', '#ef4444');
        } catch(e) {
            console.error('[Clear Site Data Error]', e);
        }
    }

    // --- 2. SMART 2-STAGE LIMIT DETECTOR (Cookie Clear -> Auto-VPN IP Switch) ---
    function triggerIPSwitchInVPN() {
        log('🔄 [VPN Auto-Switch] Запрос на смену IP в расширениях браузера...', '#f59e0b');

        // Send runtime message to VPN extensions (Urban VPN, VPNly, etc.)
        const vpnExtIds = [
            'eppiocemhmnlbhjplcgkofciiegomcon', // Urban VPN
            'igkbbjcgncjmbebllchmcaaljbdflfij', // VPNly
            'efaidnbmnnnibpcajpcglclefindmkaj'
        ];

        vpnExtIds.forEach(function(extId) {
            try {
                if (window.chrome && chrome.runtime && chrome.runtime.sendMessage) {
                    chrome.runtime.sendMessage(extId, { action: 'toggle_proxy', type: 'CHANGE_LOCATION', command: 'next' }, function(r) {});
                }
            } catch(e) {}
        });

        // Contact local Python IP switcher if active
        try {
            fetch('http://127.0.0.1:5000/switch_ip', { method: 'POST' }).then(function() {
                log('✅ Сигнал смены IP отправлен на локальный помощник!', '#34d399');
            }).catch(function() {});
        } catch(e) {}

        showStatus('🌐 ТЕКУЩИЙ IP ЗАБЛОКИРОВАН! Смените страну в расширении VPN.', '#ef4444');
    }

    function handleLimitDetected(reason) {
        if (isLimitClearedRecently) return;
        isLimitClearedRecently = true;

        if (!hasClearedCookiesForCurrentIP) {
            // Stage 1: Clear cookies & LocalStorage
            hasClearedCookiesForCurrentIP = true;
            log('🚨 ЛИМИТ ДЕТЕКТИРОВАН (' + reason + ')! [Шаг 1: Авто-сброс куки]', '#ef4444');
            clearSiteData();
        } else {
            // Stage 2: Cookies were ALREADY cleared on this IP, but limit returned! IP IS BLOCKED!
            log('🚨 ОЧИСТКА КУКИ НЕ ПОМОГЛА! ТЕКУЩИЙ IP ЗАБЛОКИРОВАН СЕРВИСОМ!', '#ef4444');
            log('⚡ [Шаг 2: Автоматический запуск смены IP в VPN расширении]', '#f59e0b');
            clearSiteData();
            triggerIPSwitchInVPN();
            hasClearedCookiesForCurrentIP = false;
        }

        setTimeout(function() { isLimitClearedRecently = false; }, 4000);
    }

    // DOM Limit Observer
    function checkLimitModalOnDOM() {
        try {
            const bodyText = document.body ? (document.body.innerText || '') : '';
            if (bodyText.indexOf("reached the limit of generations") !== -1 ||
                bodyText.indexOf("Create a free account to continue generating") !== -1 ||
                bodyText.indexOf("limit of generations as a logged-out user") !== -1 ||
                bodyText.indexOf("reached the limit") !== -1) {
                
                handleLimitDetected('Окно на экране');
            }
        } catch(e) {}
    }

    setInterval(checkLimitModalOnDOM, 1000);

    // --- 3. BASE64 TO BLOB CONVERTER WITH URL-SAFE CLEANING ---
    function base64ToBlob(base64, mimeType) {
        try {
            let b64 = base64.trim().replace(/-/g, '+').replace(/_/g, '/');
            while (b64.length % 4 !== 0) {
                b64 += '=';
            }
            const byteCharacters = atob(b64);
            const byteArrays = [];
            for (let offset = 0; offset < byteCharacters.length; offset += 512) {
                const slice = byteCharacters.slice(offset, offset + 512);
                const byteNumbers = new Array(slice.length);
                for (let i = 0; i < slice.length; i++) {
                    byteNumbers[i] = slice.charCodeAt(i);
                }
                const byteArray = new Uint8Array(byteNumbers);
                byteArrays.push(byteArray);
            }
            return new Blob(byteArrays, { type: mimeType || 'audio/mp3' });
        } catch (e) {
            return null;
        }
    }

    // --- 4. DOWNLOAD TRIGGER ---
    function triggerDownload(blob, filename) {
        if (!blob || blob.size < 1000) return;
        if (downloadedSizes.has(blob.size)) {
            log('⚠️ Пропущен дубликат размера ' + (blob.size / 1024).toFixed(1) + ' KB', '#64748b');
            return;
        }
        downloadedSizes.add(blob.size);
        lastCapturedBlob = blob;

        // Reset IP block tracking on successful audio generation
        hasClearedCookiesForCurrentIP = false;

        try {
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            setTimeout(function() {
                if (a.parentNode) a.parentNode.removeChild(a);
                URL.revokeObjectURL(url);
            }, 1500);
            log('🎉 СКАЧАН ЕДИНЫЙ ПОЛНЫЙ МЕДИАФАЙЛ: ' + filename + ' (' + (blob.size / 1024).toFixed(1) + ' KB)', '#10b981');
            showStatus('✅ Успешно скачан: ' + filename + ' (' + (blob.size / 1024).toFixed(1) + ' KB)', '#10b981');
        } catch (e) {
            log('❌ Ошибка сохранения: ' + e.message, '#ef4444');
            showStatus('❌ Ошибка сохранения: ' + e.message, '#ef4444');
        }
    }

    // --- 5. STREAMING FETCH READER & LIMIT DETECTOR ---
    function parseAndDownloadBase64Stream(text) {
        if (!text) return;
        
        // Detect quota / rate limit in response text
        if (text.indexOf('quota') !== -1 || text.indexOf('rate_limit') !== -1 || text.indexOf('unusual_activity') !== -1 || text.indexOf('anonymous_limit') !== -1 || text.indexOf('reached the limit') !== -1 || text.indexOf('logged-out user') !== -1) {
            handleLimitDetected('Сетевой ответ сервера');
            return;
        }

        let base64Parts = [];
        const lines = text.split('\n');
        
        for (let i = 0; i < lines.length; i++) {
            let line = lines[i].trim();
            if (!line) continue;
            try {
                const json = JSON.parse(line);
                if (json.audio_base64) {
                    base64Parts.push(json.audio_base64);
                }
            } catch(e) {}
        }

        if (base64Parts.length > 0) {
            const fullBase64 = base64Parts.join('');
            const blob = base64ToBlob(fullBase64, 'audio/mp3');
            if (blob && blob.size > 2000) {
                isFetchStreamHandled = true;
                log('✨ Собрана ЕДИНАЯ аудиозапись из ' + base64Parts.length + ' base64 чанков (' + (blob.size / 1024).toFixed(1) + ' KB)!', '#34d399');
                const numStr = (currentChunkIdx + 1 < 10 ? '0' : '') + (currentChunkIdx + 1);
                triggerDownload(blob, 'chunk_' + numStr + '.mp3');
            }
        }
    }

    const origFetch = window.fetch;
    window.fetch = async function() {
        const response = await origFetch.apply(this, arguments);
        try {
            const arg0 = arguments[0];
            const url = arg0 ? (typeof arg0 === 'string' ? arg0 : arg0.url) : '';

            // Detect HTTP Status limits (429 Too Many Requests, 401, 403)
            if (response.status === 429 || response.status === 401 || response.status === 403) {
                handleLimitDetected('HTTP Status ' + response.status);
            }
            
            if (url && (url.indexOf('text-to-speech') !== -1 || url.indexOf('/stream') !== -1 || url.indexOf('/v1/') !== -1)) {
                log('🌐 [Fetch Interceptor] Начало потокового чтения API...', '#fbbf24');
                isFetchStreamHandled = false;
                const clone = response.clone();

                if (clone.body && clone.body.getReader) {
                    const reader = clone.body.getReader();
                    const decoder = new TextDecoder('utf-8');
                    let fullText = '';

                    function readStream() {
                        reader.read().then(function(result) {
                            if (result.value) {
                                fullText += decoder.decode(result.value, { stream: true });
                            }
                            if (result.done) {
                                log('🏁 Поток сервера завершен. Проверка ' + fullText.length + ' символов ответа...', '#34d399');
                                parseAndDownloadBase64Stream(fullText);
                            } else {
                                readStream();
                            }
                        }).catch(function() {});
                    }
                    readStream();
                }
            }
        } catch (e) {}
        return response;
    };

    // --- 6. MEDIASOURCE ACCUMULATOR ---
    if (window.SourceBuffer && SourceBuffer.prototype) {
        const origAppend = SourceBuffer.prototype.appendBuffer;
        SourceBuffer.prototype.appendBuffer = function(buffer) {
            if (buffer && buffer.byteLength > 500) {
                mediaSourceChunks.push(buffer.slice(0));

                if (mediaSourceTimer) clearTimeout(mediaSourceTimer);
                mediaSourceTimer = setTimeout(function() {
                    if (mediaSourceChunks.length > 0 && !isFetchStreamHandled) {
                        log('📦 Сборка ' + mediaSourceChunks.length + ' чанков MediaSource...', '#a78bfa');
                        const combinedBlob = new Blob(mediaSourceChunks, { type: 'audio/mp3' });
                        mediaSourceChunks = [];
                        const numStr = (currentChunkIdx + 1 < 10 ? '0' : '') + (currentChunkIdx + 1);
                        triggerDownload(combinedBlob, 'chunk_' + numStr + '.mp3');
                    } else {
                        mediaSourceChunks = [];
                    }
                }, 3500);
            }
            return origAppend.apply(this, arguments);
        };
    }

    // --- 7. FORCE MANUAL DOWNLOAD ---
    async function forceDownloadCurrentAudio() {
        if (lastCapturedBlob) {
            const numStr = (currentChunkIdx + 1 < 10 ? '0' : '') + (currentChunkIdx + 1);
            log('📥 Ручное скачивание последнего сохраненного файла...', '#34d399');
            triggerDownload(lastCapturedBlob, 'chunk_' + numStr + '.mp3');
            return true;
        }

        showStatus('⚠️ Нажмите Play на странице ElevenLabs для запуска озвучки.', '#f59e0b');
        return false;
    }

    // --- 8. TEXT CHUNKING ---
    function splitText(text, maxLen) {
        if (!maxLen) maxLen = 920;
        const sentences = text.replace(/([.!?…])\s+/g, "$1|").split("|");
        const res = [];
        let curr = '';

        for (let i = 0; i < sentences.length; i++) {
            let s = sentences[i].trim();
            if (!s) continue;
            const sep = (curr && (s.indexOf('Часть') !== -1 || s.indexOf('[') === 0)) ? '\n\n' : ' ';
            const test = curr ? curr + sep + s : s;
            if (test.length <= maxLen) {
                curr = test;
            } else {
                if (curr) res.push(curr.trim());
                curr = s;
            }
        }
        if (curr) res.push(curr.trim());
        return res;
    }

    // --- 9. FINDERS & REACT INJECTION ---
    function findTextarea() {
        return document.querySelector('textarea') || 
               document.querySelector('div[contenteditable="true"]') || 
               document.querySelector('[role="textbox"]');
    }

    function findPlayButton() {
        let btn = document.querySelector("button[aria-label*='Play' i]") || 
                  document.querySelector("button[aria-label*='Generate' i]") || 
                  document.querySelector("button[title*='Play' i]");
        if (btn) return btn;

        const buttons = Array.from(document.querySelectorAll('button'));
        btn = buttons.find(function(b) {
            const txt = b.textContent.trim().toLowerCase();
            return txt === 'play' || txt === 'generate' || txt.indexOf('generate speech') !== -1 || txt.indexOf('озвучить') !== -1;
        });
        if (btn) return btn;

        btn = buttons.find(function(b) { return b.querySelector('svg') && b.offsetHeight > 20 && b.offsetWidth > 20; });
        return btn;
    }

    function setNativeValue(element, value) {
        if (element.tagName === 'DIV' && element.isContentEditable) {
            element.textContent = value;
            element.dispatchEvent(new Event('input', { bubbles: true }));
            return;
        }
        const descriptor = Object.getOwnPropertyDescriptor(element, 'value');
        const valueSetter = descriptor ? descriptor.set : null;
        const prototype = Object.getPrototypeOf(element);
        const prototypeDescriptor = Object.getOwnPropertyDescriptor(prototype, 'value');
        const prototypeValueSetter = prototypeDescriptor ? prototypeDescriptor.set : null;

        if (prototypeValueSetter && valueSetter !== prototypeValueSetter) {
            prototypeValueSetter.call(element, value);
        } else if (valueSetter) {
            valueSetter.call(element, value);
        } else {
            element.value = value;
        }
        element.dispatchEvent(new Event('input', { bubbles: true }));
        element.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function injectAndPlayChunk(idx) {
        if (!chunks.length || idx < 0 || idx >= chunks.length) {
            alert('Нет доступных кусков текста!');
            return;
        }
        currentChunkIdx = idx;
        const text = chunks[idx];
        const textarea = findTextarea();
        if (!textarea) {
            log('❌ Текстовое поле на странице не найдено!', '#ef4444');
            alert('Текстовое поле на странице не найдено!');
            return;
        }

        textarea.focus();
        setNativeValue(textarea, text);
        log('📝 Вставлен кусок ' + (idx + 1) + '/' + chunks.length + ' (' + text.length + ' симв.)', '#38bdf8');
        showStatus('📝 Вставлен кусок ' + (idx + 1) + '/' + chunks.length + ' (' + text.length + ' символов)', '#3b82f6');

        if (isAutoPlay) {
            setTimeout(function() {
                const playBtn = findPlayButton();
                if (playBtn) {
                    playBtn.click();
                    log('🚀 Нажата кнопка Play на странице!', '#34d399');
                    showStatus('▶️ Озвучивание куска ' + (idx + 1) + '/' + chunks.length + '...', '#f59e0b');
                } else {
                    log('⚠️ Кнопка Play не найдена автоматически.', '#fbbf24');
                    showStatus('⚠️ Нажмите кнопку Play на странице!', '#ef4444');
                }
            }, 400);
        }
        updateUI();
    }

    // --- 10. FLOATING UI WIDGET ---
    function createWidget() {
        if (document.getElementById('el-assistant-widget')) return;

        const panel = document.createElement('div');
        panel.id = 'el-assistant-widget';
        panel.innerHTML = [
            '<style>',
            '#el-assistant-widget { position: fixed; top: 70px; right: 20px; width: 350px; background: rgba(15, 23, 42, 0.96); backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.18); border-radius: 14px; padding: 14px; box-shadow: 0 20px 40px rgba(0,0,0,0.6); color: #f8fafc; font-family: system-ui, -apple-system, sans-serif; z-index: 999999; font-size: 13px; }',
            '#el-assistant-header { display: flex; justify-content: space-between; align-items: center; font-weight: 700; font-size: 14px; margin-bottom: 10px; padding-bottom: 6px; border-bottom: 1px solid rgba(255,255,255,0.1); }',
            '#el-assistant-widget textarea { width: 100%; height: 75px; background: rgba(30, 41, 59, 0.9); border: 1px solid rgba(255,255,255,0.15); border-radius: 8px; color: #e2e8f0; padding: 8px; font-size: 12px; resize: vertical; box-sizing: border-box; }',
            '.el-btn { background: linear-gradient(135deg, #6366f1, #4f46e5); color: white; border: none; border-radius: 6px; padding: 8px 12px; font-weight: 600; cursor: pointer; transition: all 0.2s; display: inline-flex; align-items: center; justify-content: center; gap: 6px; }',
            '.el-btn:hover { opacity: 0.9; transform: translateY(-1px); }',
            '.el-btn-sec { background: rgba(51, 65, 85, 0.9); color: #cbd5e1; }',
            '.el-btn-green { background: linear-gradient(135deg, #10b981, #059669); font-size: 13px; }',
            '.el-btn-red { background: linear-gradient(135deg, #ef4444, #dc2626); font-size: 11px; padding: 4px 8px; }',
            '#el-status-bar { margin-top: 8px; padding: 6px 10px; border-radius: 6px; font-size: 11px; background: rgba(30, 41, 59, 0.9); color: #94a3b8; word-break: break-word; line-height: 1.4; }',
            '#el-debug-log { height: 95px; overflow-y: auto; background: #020617; color: #38bdf8; font-family: monospace; font-size: 10px; padding: 6px; border-radius: 6px; margin-top: 8px; border: 1px solid rgba(255,255,255,0.1); }',
            '.el-flex { display: flex; gap: 8px; margin-top: 8px; }',
            '.el-badge { background: #0284c7; color: white; padding: 2px 8px; border-radius: 10px; font-size: 11px; }',
            '</style>',
            '<div id="el-assistant-header">',
            '  <span>🎙️ ElevenLabs Assistant v2.3</span>',
            '  <button id="el-btn-clean-data" class="el-btn el-btn-red" title="Очистить куки и данные сайта">🧹 Сброс куки</button>',
            '</div>',
            '<div>',
            '  <textarea id="el-full-text-input" placeholder="Вставьте весь текст сказки сюда..."></textarea>',
            '</div>',
            '<div class="el-flex">',
            '  <button id="el-btn-process" class="el-btn" style="flex: 1;">✂️ Нарезать текст</button>',
            '</div>',
            '<div id="el-chunk-controls" style="margin-top: 10px; display: none;">',
            '  <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">',
            '    <span id="el-chunk-info">Кусок 1 из 1</span>',
            '    <label style="font-size: 11px; cursor: pointer; color: #cbd5e1;">',
            '      <input type="checkbox" id="el-auto-play" checked> Авто-Play',
            '    </label>',
            '  </div>',
            '  <div class="el-flex">',
            '    <button id="el-btn-prev" class="el-btn el-btn-sec">◀</button>',
            '    <button id="el-btn-play" class="el-btn" style="flex: 1;">🚀 Озвучить кусок 1</button>',
            '    <button id="el-btn-next" class="el-btn el-btn-sec">▶</button>',
            '  </div>',
            '  <div class="el-flex">',
            '    <button id="el-btn-download-now" class="el-btn el-btn-green" style="width: 100%;">⬇️ Скачать MP3 этого куска</button>',
            '  </div>',
            '</div>',
            '<div id="el-status-bar">Готов к работе. Вставьте текст и нажмите «Нарезать».</div>',
            '<div id="el-debug-log"><div>[Логи дебага появится здесь]</div></div>'
        ].join('');

        document.body.appendChild(panel);
        log('Запущен смарт-скрипт v2.3 с 2-этапным детектором (Куки -> Авто-смена IP)!');

        document.getElementById('el-btn-clean-data').addEventListener('click', function() {
            clearSiteData();
        });

        document.getElementById('el-btn-process').addEventListener('click', function() {
            const raw = document.getElementById('el-full-text-input').value.trim();
            if (!raw) {
                alert('Вставьте текст сказки!');
                return;
            }
            chunks = splitText(raw);
            currentChunkIdx = 0;
            document.getElementById('el-chunk-controls').style.display = 'block';
            log('✂️ Текст нарезан на ' + chunks.length + ' кусков.', '#34d399');
            showStatus('✅ Нарезано на ' + chunks.length + ' кусков. Жмите «🚀 Озвучить кусок»!', '#10b981');
            updateUI();
        });

        document.getElementById('el-btn-play').addEventListener('click', function() { injectAndPlayChunk(currentChunkIdx); });
        document.getElementById('el-btn-download-now').addEventListener('click', function() { forceDownloadCurrentAudio(); });
        document.getElementById('el-btn-next').addEventListener('click', function() {
            if (currentChunkIdx < chunks.length - 1) {
                currentChunkIdx++;
                injectAndPlayChunk(currentChunkIdx);
            }
        });
        document.getElementById('el-btn-prev').addEventListener('click', function() {
            if (currentChunkIdx > 0) {
                currentChunkIdx--;
                injectAndPlayChunk(currentChunkIdx);
            }
        });
        document.getElementById('el-auto-play').addEventListener('change', function(e) {
            isAutoPlay = e.target.checked;
        });
    }

    function updateUI() {
        const badge = document.getElementById('el-chunk-badge');
        const info = document.getElementById('el-chunk-info');
        const playBtn = document.getElementById('el-btn-play');

        if (badge) badge.textContent = chunks.length + ' кусков';
        if (info && chunks.length) {
            const len = chunks[currentChunkIdx] ? chunks[currentChunkIdx].length : 0;
            info.textContent = 'Кусок ' + (currentChunkIdx + 1) + ' из ' + chunks.length + ' (' + len + ' симв.)';
        }
        if (playBtn && chunks.length) {
            playBtn.textContent = '🚀 Озвучить кусок ' + (currentChunkIdx + 1);
        }
    }

    if (document.readyState === 'loading') {
        window.addEventListener('DOMContentLoaded', function() { setTimeout(createWidget, 600); });
    } else {
        setTimeout(createWidget, 600);
    }
})();
