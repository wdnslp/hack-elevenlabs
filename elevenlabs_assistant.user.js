// ==UserScript==
// @name         ElevenLabs Assistant
// @namespace    http://tampermonkey.net/
// @version      5.0
// @description  ElevenLabs TTS Assistant with Smart 2-Stage Limit Detector, Local API Server Direct Upload & Full Auto-Batch Workflow
// @match        https://elevenlabs.io/*
// @grant        GM_xmlhttpRequest
// @grant        GM_setValue
// @grant        GM_getValue
// @connect      127.0.0.1
// @connect      localhost
// @run-at       document-start
// ==/UserScript==














(function () {
    'use strict';

    let currentChunkIdx = 0;
    let chunks = [];
    let isAutoPlay = true;
    let lastCapturedBlob = null;
    let downloadedSizes = new Set();
    let isLimitClearedRecently = false;
    let activeStoryData = null;
    let lastHandledStoryId = "";

    const LOCAL_SERVER_STORY_URL = "http://127.0.0.1:5000/api/story";
    const LOCAL_SERVER_UPLOAD_URL = "http://127.0.0.1:5000/api/upload_chunk";

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

    // --- LOCAL SERVER FETCHING & BATCH POLLING ---
    function fetchStoryFromLocalServer(isAutoPoll) {
        if (!isAutoPoll) {
            log('📡 Запрос истории с локального сервера (' + LOCAL_SERVER_STORY_URL + ')...', '#38bdf8');
            showStatus('📡 Запрос истории с локального сервера Python...', '#3b82f6');
        }

        const processResponse = function (dataStr) {
            try {
                const data = JSON.parse(dataStr);
                if (!data || !data.story_id) return;

                if (data.story_id === lastHandledStoryId && isAutoPoll) {
                    return; // No new story yet
                }

                const textToUse = data.formatted_text || data.full_text || (data.title ? (data.title + "\n\n" + (data.body || "")) : "");
                if (textToUse && textToUse.trim().length > 10) {
                    activeStoryData = data;
                    lastHandledStoryId = data.story_id;

                    const inputEl = document.getElementById('el-full-text-input');
                    if (inputEl) inputEl.value = textToUse.trim();

                    chunks = splitText(textToUse.trim());
                    currentChunkIdx = (data.received_chunks_count && data.received_chunks_count < chunks.length) ? data.received_chunks_count : 0;
                    document.getElementById('el-chunk-controls').style.display = 'block';

                    const storyTitle = data.title ? (data.title.substring(0, 45) + '...') : 'История';
                    const subInfo = data.subreddit ? ('r/' + data.subreddit) : 'Reddit';
                    const batchProgress = (data.story_idx && data.total_stories) ? (' [' + data.story_idx + '/' + data.total_stories + ']') : '';

                    log('🎉 АВТО-ПОДТЯНУТА ИСТОРИЯ' + batchProgress + ' [' + subInfo + ']: "' + storyTitle + '" (' + chunks.length + ' кусков)!', '#10b981');
                    showStatus('✅ Подтянута история' + batchProgress + ': "' + storyTitle + '" (' + chunks.length + ' кусков)', '#10b981');
                    updateUI();

                    if (isAutoPlay && chunks.length > 0 && currentChunkIdx < chunks.length) {
                        log('▶️ [АВТО-СТАРТ] Автоматический запуск куска ' + (currentChunkIdx + 1) + '/' + chunks.length + '...', '#34d399');
                        setTimeout(function () {
                            injectAndPlayChunk(currentChunkIdx);
                        }, 1200);
                    }
                } else if (!isAutoPoll) {
                    log('⚠️ На сервере нет готовой истории (статус: idle).', '#f59e0b');
                    showStatus('⚠️ На локальном сервере нет подгруженной истории.', '#f59e0b');
                }
            } catch (e) {
                if (!isAutoPoll) {
                    log('❌ Ошибка парсинга ответа сервера: ' + e.message, '#ef4444');
                    showStatus('❌ Ошибка парсинга ответа сервера.', '#ef4444');
                }
            }
        };

        if (typeof GM_xmlhttpRequest === 'function') {
            GM_xmlhttpRequest({
                method: "GET",
                url: LOCAL_SERVER_STORY_URL,
                onload: function (res) { processResponse(res.responseText); }
            });
        } else {
            fetch(LOCAL_SERVER_STORY_URL)
                .then(r => r.text())
                .then(txt => processResponse(txt))
                .catch(err => { });
        }
    }

    // Auto-poll server for next story in batch every 3 seconds
    setInterval(function () {
        fetchStoryFromLocalServer(true);
    }, 3000);

    // --- UPLOAD AUDIO CHUNK DIRECTLY TO PYTHON SERVER ---
    function sendAudioChunkToServer(blob, chunkIdx, totalChunks) {
        if (!blob) return;
        const storyId = (activeStoryData && activeStoryData.story_id) ? activeStoryData.story_id : "default_story";

        log('🚀 Отправка аудио куска ' + (chunkIdx + 1) + '/' + totalChunks + ' на локальный Python сервер...', '#a78bfa');
        showStatus('🚀 Отправка куска ' + (chunkIdx + 1) + '/' + totalChunks + ' в Python...', '#a78bfa');

        const reader = new FileReader();
        reader.onloadend = function () {
            const base64Data = reader.result.split(',')[1] || reader.result;
            const payload = JSON.stringify({
                story_id: storyId,
                chunk_idx: chunkIdx,
                total_chunks: totalChunks,
                audio_base64: base64Data
            });

            const onUploadSuccess = function (respStr) {
                try {
                    setHasGeneratedOnCurrentCookie(true);
                    const resp = JSON.parse(respStr);
                    log('✅ КУСОК ' + (chunkIdx + 1) + '/' + totalChunks + ' УСПЕШНО ПЕРЕДАН В PYTHON! (' + resp.received_count + '/' + resp.total_chunks + ')', '#10b981');
                    if (resp.is_complete) {
                        log('🎉 ВСЕ КУСКИ ИСТОРИИ ОЗВУЧЕНЫ! Python начал генерацию видео...', '#f59e0b');
                        showStatus('🎉 История полностью передана! Ожидайте следующую...', '#10b981');
                        setTimeout(function () {
                            fetchStoryFromLocalServer(true);
                        }, 2000);
                    } else {
                        showStatus('✅ Кусок ' + (chunkIdx + 1) + '/' + totalChunks + ' передан в Python.', '#10b981');
                        if (isAutoPlay && currentChunkIdx < totalChunks - 1) {
                            currentChunkIdx++;
                            log('⏭️ [АВТО-СЛЕДУЮЩИЙ КУСОК] Переход к куску ' + (currentChunkIdx + 1) + '/' + totalChunks + '...', '#38bdf8');
                            setTimeout(function () {
                                injectAndPlayChunk(currentChunkIdx);
                            }, 1000);
                        }
                    }
                } catch (e) { }
            };




            if (typeof GM_xmlhttpRequest === 'function') {
                GM_xmlhttpRequest({
                    method: "POST",
                    url: LOCAL_SERVER_UPLOAD_URL,
                    headers: { "Content-Type": "application/json" },
                    data: payload,
                    onload: function (res) { onUploadSuccess(res.responseText); },
                    onerror: function (err) {
                        log('❌ Ошибка отправки аудио в Python (GM_XHR): ' + (err ? (err.statusText || err.responseText || JSON.stringify(err)) : 'Сбой сети'), '#ef4444');
                        showStatus('❌ Ошибка связи с Python при отправке аудио!', '#ef4444');
                    }
                });
            } else {
                fetch(LOCAL_SERVER_UPLOAD_URL, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: payload
                })
                    .then(r => r.text())
                    .then(txt => onUploadSuccess(txt))
                    .catch(err => {
                        log('❌ Ошибка отправки аудио в Python (Fetch): ' + err.message, '#ef4444');
                        showStatus('❌ Ошибка связи с Python при отправке аудио!', '#ef4444');
                    });
            }
        };
        reader.readAsDataURL(blob);
    }

    function notifyPythonServerLimitReached(reason, resets) {
        const payload = JSON.stringify({
            reason: reason,
            resets: resets,
            timestamp: Date.now()
        });
        const url = "http://127.0.0.1:5000/api/limit_reached";
        if (typeof GM_xmlhttpRequest === 'function') {
            GM_xmlhttpRequest({
                method: "POST",
                url: url,
                headers: { "Content-Type": "application/json" },
                data: payload
            });
        } else {
            fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: payload }).catch(() => {});
        }
    }

    // --- 1. COOKIE AND SITE STORAGE AUTO-CLEANER ---
    function clearSiteData() {
        try {
            window.localStorage.clear();
            window.sessionStorage.clear();
            document.cookie.split(";").forEach(function (c) {
                document.cookie = c.replace(/^ +/, "").replace(/=.*/, "=;expires=" + new Date().toUTCString() + ";path=/;domain=" + window.location.hostname);
                document.cookie = c.replace(/^ +/, "").replace(/=.*/, "=;expires=" + new Date().toUTCString() + ";path=/");
            });
            log('🧹 АВТО-ОЧИСТКА: Куки, LocalStorage и сессии ElevenLabs сброшены!', '#f59e0b');
            showStatus('🚨 Лимит! Куки очищены. Если окно появится снова — требуется смена IP в VPN.', '#ef4444');
        } catch (e) {
            console.error('[Clear Site Data Error]', e);
        }
    }

    // --- 2. SMART 2-STAGE LIMIT DETECTOR WITH GENERATION TRACKING ---
    function getHasGeneratedOnCurrentCookie() {
        try {
            if (typeof GM_getValue === 'function') return GM_getValue('el_has_generated', '0') === '1';
            return sessionStorage.getItem('el_has_generated') === '1';
        } catch (e) { return false; }
    }

    function setHasGeneratedOnCurrentCookie(val) {
        try {
            const strVal = val ? '1' : '0';
            if (typeof GM_setValue === 'function') GM_setValue('el_has_generated', strVal);
            sessionStorage.setItem('el_has_generated', strVal);
        } catch (e) { }
    }

    function triggerIPSwitchInVPN() {
        log('⚡ [АВТО-РОТАЦИЯ] IP заблокирован. Сигнал в Python: автоматическая смена IP через Cloudflare WARP...', '#a78bfa');
        showStatus('⚡ Авто-смена IP через Cloudflare WARP... Страница перезагрузится через 3 сек', '#a78bfa');
        notifyPythonServerLimitReached('IP_HARD_BLOCKED_ZERO_GENERATIONS', 0);
        setTimeout(function () {
            window.location.reload();
        }, 3500);
    }


    function handleLimitDetected(reason) {
        if (isLimitClearedRecently) return;
        isLimitClearedRecently = true;

        const hasGenerated = getHasGeneratedOnCurrentCookie();

        if (hasGenerated) {
            log('🚨 ЛИМИТ ДЕТЕКТИРОВАН (' + reason + ')! [Были успехи -> Авто-сброс куки + F5]', '#f59e0b');
            setHasGeneratedOnCurrentCookie(false);
            clearSiteData();
            setTimeout(function () {
                window.location.reload();
            }, 600);
        } else {
            log('🚨 ОЧИСТКА КУКИ НЕ ПОМОГЛА (0 генераций после сброса кук)! ТЕКУЩИЙ IP ЗАБЛОКИРОВАН!', '#ef4444');
            clearSiteData();
            triggerIPSwitchInVPN();
        }

        setTimeout(function () { isLimitClearedRecently = false; }, 4000);
    }


    function checkLimitModalOnDOM() {
        try {
            const bodyText = document.body ? (document.body.innerText || '') : '';
            if (bodyText.indexOf("reached the limit of generations") !== -1 ||
                bodyText.indexOf("Create a free account to continue generating") !== -1 ||
                bodyText.indexOf("limit of generations as a logged-out user") !== -1 ||
                bodyText.indexOf("Unusual activity detected") !== -1) {

                handleLimitDetected('DOM Модальное окно лимита');
            }
        } catch (e) { }
    }

    setInterval(checkLimitModalOnDOM, 2500);


    // --- 3. BASE64 TO BLOB CONVERTER WITH URL-SAFE CLEANING ---
    function base64ToBlob(base64, mimeType) {
        try {
            const byteCharacters = atob(base64);
            const byteNumbers = new Array(byteCharacters.length);
            for (let i = 0; i < byteCharacters.length; i++) {
                byteNumbers[i] = byteCharacters.charCodeAt(i);
            }
            const byteArray = new Uint8Array(byteNumbers);
            return new Blob([byteArray], { type: mimeType || 'audio/mp3' });
        } catch (e) {
            return null;
        }
    }

    // --- 4. DOWNLOAD & AUTO-UPLOAD TRIGGER ---
    function triggerDownload(blob, filename) {
        if (!blob || blob.size < 3000) return;
        if (downloadedSizes.has(blob.size)) return;
        downloadedSizes.add(blob.size);
        lastCapturedBlob = blob;
        hasClearedCookiesForCurrentIP = false;

        // Auto-upload chunk directly to Python server over HTTP API (no browser disk file download needed)
        sendAudioChunkToServer(blob, currentChunkIdx, chunks.length || 1);
        log('⚡ АУДИО ОЗВУЧЕНО: (' + (blob.size / 1024).toFixed(1) + ' KB) -> Отправлено в Python!', '#10b981');
    }

    // --- 5. STREAMING FETCH READER & LIMIT DETECTOR ---
    function parseAndDownloadBase64Stream(text) {
        if (!text) return;

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
            } catch (e) { }
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
    window.fetch = async function () {
        const response = await origFetch.apply(this, arguments);
        try {
            const arg0 = arguments[0];
            const url = arg0 ? (typeof arg0 === 'string' ? arg0 : arg0.url) : '';

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
                        reader.read().then(function (result) {
                            if (result.value) {
                                fullText += decoder.decode(result.value, { stream: true });
                            }
                            if (result.done) {
                                log('🏁 Поток сервера завершен. Проверка ' + fullText.length + ' символов ответа...', '#34d399');
                                parseAndDownloadBase64Stream(fullText);
                            } else {
                                readStream();
                            }
                        }).catch(function () { });
                    }
                    readStream();
                }
            }
        } catch (e) { }
        return response;
    };

    // --- 6. MEDIASOURCE ACCUMULATOR ---
    if (window.SourceBuffer && SourceBuffer.prototype) {
        const origAppend = SourceBuffer.prototype.appendBuffer;
        SourceBuffer.prototype.appendBuffer = function (buffer) {
            if (buffer && buffer.byteLength > 500) {
                mediaSourceChunks.push(buffer.slice(0));

                if (mediaSourceTimer) clearTimeout(mediaSourceTimer);
                mediaSourceTimer = setTimeout(function () {
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
        btn = buttons.find(function (b) {
            const txt = b.textContent.trim().toLowerCase();
            return txt === 'play' || txt === 'generate' || txt.indexOf('generate speech') !== -1 || txt.indexOf('озвучить') !== -1;
        });
        if (btn) return btn;

        btn = buttons.find(function (b) { return b.querySelector('svg') && b.offsetHeight > 20 && b.offsetWidth > 20; });
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
            setTimeout(function () {
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

    function updateUI() {
        const infoEl = document.getElementById('el-chunk-info');
        if (infoEl) {
            const charCount = chunks[currentChunkIdx] ? chunks[currentChunkIdx].length : 0;
            infoEl.textContent = 'Кусок ' + (currentChunkIdx + 1) + ' из ' + chunks.length + ' (' + charCount + ' симв.)';
        }
        const playBtn = document.getElementById('el-btn-play');
        if (playBtn) {
            playBtn.textContent = '🚀 Озвучить кусок ' + (currentChunkIdx + 1);
        }
    }

    // --- 1.1 AUTO VOICE & LANGUAGE SELECTORS ---
    function openDropdownElement(element) {
        if (!element) return;
        try { element.focus(); } catch (e) { }

        const targets = [element, element.parentElement].filter(Boolean);
        targets.forEach(t => {
            try { t.click(); } catch (e) { }
            const rect = t.getBoundingClientRect();
            const x = rect.left + rect.width / 2;
            const y = rect.top + rect.height / 2;

            ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(eventType => {
                try {
                    const evt = new PointerEvent(eventType, {
                        bubbles: true, cancelable: true, view: window,
                        clientX: x, clientY: y, button: 0, buttons: 1
                    });
                    t.dispatchEvent(evt);
                } catch (e) { }
            });
        });
    }

    function scrollWithMouseWheel(container, deltaY) {
        if (!container) return;
        try {
            container.scrollTop += deltaY;
            const evt = new WheelEvent('wheel', {
                bubbles: true,
                cancelable: true,
                view: window,
                deltaY: deltaY,
                deltaMode: 0
            });
            container.dispatchEvent(evt);
        } catch (e) { }
    }

    function clickOptionRow(element) {
        if (!element) return;
        try { element.scrollIntoView({ block: 'center', inline: 'center' }); } catch (e) { }
        try { element.focus(); } catch (e) { }

        const targets = [
            element,
            element.parentElement,
            element.closest('button'),
            element.closest('li'),
            element.closest('[role="option"]'),
            element.closest('div[tabindex]')
        ].filter(Boolean);

        const uniqueTargets = Array.from(new Set(targets));

        uniqueTargets.forEach(t => {
            try { t.click(); } catch (e) { }
            const rect = t.getBoundingClientRect();
            const x = rect.left + rect.width / 2;
            const y = rect.top + rect.height / 2;

            ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(eventType => {
                try {
                    const evt = new PointerEvent(eventType, {
                        bubbles: true, cancelable: true, view: window,
                        clientX: x, clientY: y, button: 0, buttons: 1
                    });
                    t.dispatchEvent(evt);
                } catch (e) { }
            });
        });
    }

    function findAndClickOptionWithScroll(targetTexts, callback, isExactWordOnly) {
        const getActivePopovers = () => {
            const selectors = '[role="listbox"], [role="menu"], [data-radix-popper-content-wrapper], [aria-modal="true"], div[class*="select"], div[class*="dropdown"], div[class*="menu"], div[style*="position: absolute"], div[style*="position: fixed"]';
            return Array.from(document.querySelectorAll(selectors)).filter(c => c.offsetHeight > 50 && c.offsetWidth > 50);
        };

        const popovers = getActivePopovers();
        const container = popovers[popovers.length - 1];

        if (!container) {
            log('⚠️ Выпадающее окно (popover) не появилось на экране.', '#f59e0b');
            if (callback) callback(false);
            return;
        }

        // Try using search input if available inside popover
        const searchInput = container.querySelector('input[placeholder*="Search" i], input[type="search"]') || document.querySelector('input[placeholder*="Search" i], input[type="search"]');
        if (searchInput && isExactWordOnly) {
            searchInput.focus();
            setNativeValue(searchInput, 'Den');
        }

        function searchPopoverDOM() {
            const nodes = Array.from(container.querySelectorAll('button, div, li, span, p, a, [role="option"]'));
            return nodes.find(el => {
                const txt = (el.textContent || '').trim().toLowerCase();
                if (!txt || txt.length > 80) return false;

                const isMatch = targetTexts.some(t => {
                    const lowT = t.toLowerCase();
                    if (lowT === 'den' || isExactWordOnly) {
                        if (txt.includes('denis') || txt.includes('dennis')) return false;
                        return txt === 'den' ||
                            txt.startsWith('den ') ||
                            txt.startsWith('den\n') ||
                            txt.startsWith('den (') ||
                            txt.startsWith('den-');
                    }
                    return txt === lowT ||
                        txt.startsWith(lowT + ' ') ||
                        txt.startsWith(lowT + '\n') ||
                        txt.indexOf(lowT) !== -1;
                });

                if (!isMatch) return false;

                const hasMatchingChild = Array.from(el.children).some(child => {
                    const cTxt = (child.textContent || '').trim().toLowerCase();
                    if (targetTexts.some(t => t.toLowerCase() === 'den')) {
                        if (cTxt.includes('denis') || cTxt.includes('dennis')) return false;
                        return cTxt === 'den' || cTxt.startsWith('den ') || cTxt.startsWith('den\n') || cTxt.startsWith('den (');
                    }
                    return targetTexts.some(t => cTxt.includes(t.toLowerCase()));
                });

                return !hasMatchingChild && el.offsetHeight > 0 && el.offsetHeight < 120;
            });
        }

        let match = searchPopoverDOM();
        if (match) {
            log('✨ Найден элемент в списке: "' + match.textContent.trim().substring(0, 35) + '"! Кликаем...', '#10b981');
            clickOptionRow(match);
            setTimeout(function () {
                if (callback) callback(true);
            }, 600);
            return;
        }

        let stepCount = 0;
        const maxSteps = 45;

        const interval = setInterval(function () {
            stepCount++;
            scrollWithMouseWheel(container, 500); // 500px step per scroll!
            match = searchPopoverDOM();

            if (match || stepCount >= maxSteps) {
                clearInterval(interval);
                if (match) {
                    log('✨ Найден вариант при турбо-скролле (500px): "' + match.textContent.trim().substring(0, 35) + '"! Кликаем...', '#10b981');
                    clickOptionRow(match);
                    setTimeout(function () {
                        if (callback) callback(true);
                    }, 500);
                } else {
                    setTimeout(function () {
                        if (callback) callback(false);
                    }, 300);
                }
            }
        }, 45);
    }






    function selectRussianLanguage(callback) {
        const buttons = Array.from(document.querySelectorAll('button, div[role="button"]'));
        let langPicker = buttons.find(b => {
            const txt = (b.textContent || '').trim().toLowerCase();
            const aria = (b.getAttribute('aria-label') || '').toLowerCase();
            return txt.includes('english') || txt.includes('russian') || txt.includes('русский') || aria.includes('language');
        });

        if (!langPicker) {
            log('⚠️ Выпадающее меню выбора языка не найдено на странице.', '#f59e0b');
            if (callback) callback();
            return;
        }

        if (langPicker.textContent.includes('Russian') || langPicker.textContent.includes('Русский')) {
            log('✅ Язык "Русский" уже выбран.', '#10b981');
            if (callback) callback();
            return;
        }

        log('🌐 [Шаг 1/2] Быстрое открытие меню языка...', '#38bdf8');
        openDropdownElement(langPicker);

        setTimeout(function () {
            findAndClickOptionWithScroll(['Russian', 'Русский'], function (found) {
                if (found) {
                    log('✨ Успешно выбран язык "Русский"!', '#10b981');
                } else {
                    log('⚠️ Элемент языка "Русский" не найден в списке.', '#f59e0b');
                }
                setTimeout(function () {
                    if (callback) callback();
                }, 300);
            });
        }, 200);
    }

    function selectVoiceDen(callback) {
        const buttons = Array.from(document.querySelectorAll('button, div[role="button"]'));
        let voicePicker = buttons.find(b => {
            const txt = (b.textContent || '').trim();
            const aria = (b.getAttribute('aria-label') || '').toLowerCase();
            return (aria.includes('voice') || b.querySelector('svg')) &&
                !txt.toLowerCase().includes('english') &&
                !txt.toLowerCase().includes('russian') &&
                !txt.toLowerCase().includes('русский') &&
                !txt.toLowerCase().includes('play') &&
                !txt.toLowerCase().includes('generate') &&
                (b.offsetWidth > 40 && b.offsetHeight > 20);
        });

        if (!voicePicker) {
            voicePicker = buttons.find(b => {
                const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                return aria.includes('voice') || b.getAttribute('aria-haspopup') === 'listbox' || b.getAttribute('aria-haspopup') === 'menu';
            });
        }

        if (!voicePicker) {
            log('⚠️ Выпадающее меню выбора голоса не найдено.', '#f59e0b');
            if (callback) callback();
            return;
        }

        const voiceTxt = voicePicker.textContent.trim();
        if (!voiceTxt.toLowerCase().includes('denis') && (voiceTxt === 'Den' || voiceTxt.startsWith('Den ') || voiceTxt.startsWith('Den\n'))) {
            log('✅ Голос "Den" уже выбран.', '#10b981');
            if (callback) callback();
            return;
        }

        log('🎙️ [Шаг 2/2] Быстрое открытие меню голоса (текущий: "' + voiceTxt + '")...', '#38bdf8');
        openDropdownElement(voicePicker);

        setTimeout(function () {
            findAndClickOptionWithScroll(['Den'], function (found) {
                if (found) {
                    log('✨ Успешно выбран голос "Den"!', '#10b981');
                } else {
                    log('⚠️ Голос "Den" не найден в списке.', '#f59e0b');
                }
                setTimeout(function () {
                    if (callback) callback();
                }, 300);
            }, true); // isExactWordOnly = true
        }, 200);
    }



    function autoSelectLanguageAndVoice() {
        log('⏳ Ожидание полной подгрузки элементов страницы и VPN (1 сек)...', '#38bdf8');
        setTimeout(function () {
            log('⚙️ Последовательная настройка: 1) Русский язык -> 2) Голос Den...', '#a78bfa');
            selectRussianLanguage(function () {
                selectVoiceDen(function () {
                    log('✅ Настройка языка и голоса завершена!', '#10b981');
                    if (isAutoPlay && chunks.length > 0 && currentChunkIdx < chunks.length) {
                        setTimeout(function () {
                            log('🚀 [АВТО-ПОДХВАТ] Запуск генерации куска ' + (currentChunkIdx + 1) + '/' + chunks.length + '...', '#34d399');
                            injectAndPlayChunk(currentChunkIdx);
                        }, 800);
                    }
                });
            });
        }, 1000);
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
            '.el-btn-sky { background: linear-gradient(135deg, #0284c7, #0369a1); font-size: 12px; width: 100%; margin-bottom: 6px; }',
            '.el-btn-green { background: linear-gradient(135deg, #10b981, #059669); font-size: 13px; }',
            '.el-btn-red { background: linear-gradient(135deg, #ef4444, #dc2626); font-size: 11px; padding: 4px 8px; }',
            '#el-status-bar { margin-top: 8px; padding: 6px 10px; border-radius: 6px; font-size: 11px; background: rgba(30, 41, 59, 0.9); color: #94a3b8; word-break: break-word; line-height: 1.4; }',
            '#el-debug-log { height: 95px; overflow-y: auto; background: #020617; color: #38bdf8; font-family: monospace; font-size: 10px; padding: 6px; border-radius: 6px; margin-top: 8px; border: 1px solid rgba(255,255,255,0.1); }',
            '.el-flex { display: flex; gap: 8px; margin-top: 8px; }',
            '.el-badge { background: #0284c7; color: white; padding: 2px 8px; border-radius: 10px; font-size: 11px; }',
            '</style>',
            '<div id="el-assistant-header">',
            '  <span>🎙️ ElevenLabs v5.0 (Full Auto)</span>',
            '  <div style="display: flex; gap: 4px;">',
            '    <button id="el-btn-auto-voice" class="el-btn el-btn-sec" style="font-size: 11px; padding: 4px 8px;" title="Выбрать голос Den и русский язык">🎙️ Den + RU</button>',
            '    <button id="el-btn-clean-data" class="el-btn el-btn-red" title="Очистить куки и данные сайта">🧹 Сброс куки</button>',
            '  </div>',
            '</div>',
            '<div>',
            '  <button id="el-btn-fetch-server" class="el-btn el-btn-sky">📡 Подтянуть историю с сервера (127.0.0.1:5000)</button>',
            '  <textarea id="el-full-text-input" placeholder="Вставьте весь текст сказки сюда или нажмите «Подтянуть с сервера»..."></textarea>',
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
            '<div id="el-status-bar">Готов к работе. Включена ПОЛНАЯ автоматизация с Python!</div>',
            '<div id="el-debug-log"><div>[Логи дебага появятся здесь]</div></div>'
        ].join('');

        document.body.appendChild(panel);
        log('Запущен ElevenLabs Assistant v5.0 (Full Auto)!');















        document.getElementById('el-btn-auto-voice').addEventListener('click', function () {
            autoSelectLanguageAndVoice();
        });

        document.getElementById('el-btn-clean-data').addEventListener('click', function () {
            clearSiteData();
        });

        document.getElementById('el-btn-fetch-server').addEventListener('click', function () {
            fetchStoryFromLocalServer(false);
        });

        document.getElementById('el-btn-process').addEventListener('click', function () {
            const raw = document.getElementById('el-full-text-input').value.trim();
            if (!raw) {
                alert('Вставьте текст сказки или подтяните с сервера!');
                return;
            }
            chunks = splitText(raw);
            currentChunkIdx = 0;
            document.getElementById('el-chunk-controls').style.display = 'block';
            log('✂️ Текст нарезан на ' + chunks.length + ' кусков.', '#34d399');
            showStatus('✅ Нарезано на ' + chunks.length + ' кусков. Жмите «🚀 Озвучить кусок»!', '#10b981');
            updateUI();
        });

        document.getElementById('el-btn-play').addEventListener('click', function () { injectAndPlayChunk(currentChunkIdx); });
        document.getElementById('el-btn-download-now').addEventListener('click', function () { forceDownloadCurrentAudio(); });
        document.getElementById('el-btn-next').addEventListener('click', function () {
            if (currentChunkIdx < chunks.length - 1) {
                currentChunkIdx++;
                injectAndPlayChunk(currentChunkIdx);
            }
        });
        document.getElementById('el-btn-prev').addEventListener('click', function () {
            if (currentChunkIdx > 0) {
                currentChunkIdx--;
                injectAndPlayChunk(currentChunkIdx);
            }
        });
        document.getElementById('el-auto-play').addEventListener('change', function (e) {
            isAutoPlay = e.target.checked;
        });

        setTimeout(function () { fetchStoryFromLocalServer(false); }, 1500);
        setTimeout(function () { autoSelectLanguageAndVoice(); }, 2800);
    }

    if (document.readyState === 'loading') {
        window.addEventListener('DOMContentLoaded', function () { setTimeout(createWidget, 1000); });
    } else {
        setTimeout(createWidget, 1000);
    }

})();
