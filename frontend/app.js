(() => {
  'use strict';

  // ────────────── DOM refs ──────────────
  const $ = (id) => document.getElementById(id);
  const form        = $('text-form');
  const textarea    = $('question');
  const charN       = $('char-n');
  const submitBtn   = $('submit-btn');
  const micBtn      = $('mic-btn');
  const micWrap     = $('mic-wrap');
  const micLabel    = $('mic-label');
  const micHint     = $('mic-hint');
  const micTimer    = $('mic-timer');
  const micBars     = $('mic-bars');
  const results     = $('results');
  const emptyState  = $('empty-state');
  const errorSlot   = $('error-slot');
  const ttsAudio    = $('tts-audio');
  const typeToggle  = $('type-toggle');
  const composerShell = $('composer-shell');

  // ────────────── State ──────────────
  let micState = 'idle';
  let mediaRecorder = null;
  let audioChunks = [];
  let recordStart = 0;
  let recordTimerId = null;
  let isSubmitting = false;

  // Audio-reactive bars
  let audioCtx = null;
  let analyser = null;
  let rafId = null;
  let barEls = micBars ? Array.from(micBars.querySelectorAll('.bar')) : [];

  // ────────────── Helpers ──────────────
  const setBusy = (busy) => {
    isSubmitting = busy;
    submitBtn.disabled = busy;
    submitBtn.classList.toggle('is-loading', busy);
  };
  const escapeHtml = (s) => String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  const showError = (title, msg) => {
    errorSlot.innerHTML = `
      <div class="error-banner" role="alert">
        <div class="err-icon" aria-hidden="true">!</div>
        <div class="err-content">
          <p class="err-title">${escapeHtml(title)}</p>
          <p class="err-msg">${escapeHtml(msg)}</p>
        </div>
        <button class="err-dismiss" type="button" aria-label="إغلاق">إغلاق</button>
      </div>`;
    errorSlot.querySelector('.err-dismiss').addEventListener('click', () => {
      errorSlot.innerHTML = '';
    });
    // ensure type composer is visible when there's a text-side error
    openComposer(true);
  };
  const clearError = () => { errorSlot.innerHTML = ''; };
  const highlightSQL = (raw) => {
    const KW = /\b(SELECT|FROM|WHERE|GROUP\s+BY|ORDER\s+BY|HAVING|LIMIT|OFFSET|JOIN|LEFT|RIGHT|INNER|OUTER|FULL|ON|AS|AND|OR|NOT|IN|IS|NULL|LIKE|BETWEEN|CASE|WHEN|THEN|ELSE|END|INSERT|UPDATE|DELETE|INTO|VALUES|SET|CREATE|TABLE|ALTER|DROP|DISTINCT|UNION|ALL|COUNT|SUM|AVG|MIN|MAX|DATE|YEAR|MONTH|DAY|NOW|CURRENT_DATE|CURRENT_TIMESTAMP|DESC|ASC|TRUE|FALSE)\b/gi;
    let out = escapeHtml(raw);
    out = out.replace(/('([^']|'')*')/g, '<span class="s">$1</span>');
    out = out.replace(/\b(\d+(?:\.\d+)?)\b/g, '<span class="n">$1</span>');
    out = out.replace(/(--[^\n]*)/g, '<span class="c">$1</span>');
    out = out.replace(KW, '<span class="k">$1</span>');
    return out;
  };
  const fmtTime = (ms) => {
    const s = Math.floor(ms / 1000);
    return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
  };

  // ────────────── Composer toggle ──────────────
  const openComposer = (open) => {
    composerShell.dataset.open = open ? 'true' : 'false';
    typeToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) setTimeout(() => textarea.focus(), 240);
  };
  typeToggle.addEventListener('click', () => {
    openComposer(composerShell.dataset.open !== 'true');
  });

  // ────────────── Suggestion chips ──────────────
  document.querySelectorAll('.v-chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      const text = chip.dataset.suggest || '';
      textarea.value = text;
      charN.textContent = text.length;
      openComposer(true);
    });
  });

  // ────────────── Char counter ──────────────
  textarea.addEventListener('input', () => {
    charN.textContent = textarea.value.length;
  });

  // ────────────── Submit (text) ──────────────
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (isSubmitting) return;
    const text = textarea.value.trim();
    if (!text) {
      showError('السؤال فارغ', 'يرجى كتابة سؤالك قبل الإرسال.');
      textarea.focus();
      return;
    }
    clearError();
    setBusy(true);
    renderLoading(text);
    try {
      const body = new FormData();
      body.append('text', text);
      const res = await fetch('/process_text', { method: 'POST', body });
      const data = await res.json();
      if (!res.ok || data.error) renderError(data.error || `خطأ في الخادم (${res.status})`);
      else renderResult(data);
    } catch {
      renderError('تعذّر الاتصال بالخادم. تحقّق من اتصالك ثم حاول مجدّداً.');
    } finally {
      setBusy(false);
    }
  });
  textarea.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  // ────────────── Mic state ──────────────
  const setMicState = (state) => {
    micState = state;
    micWrap.classList.toggle('is-recording', state === 'recording');
    micWrap.classList.toggle('is-processing', state === 'processing');
    micBtn.setAttribute('aria-pressed', state === 'recording' ? 'true' : 'false');

    if (state === 'idle') {
      micLabel.textContent = 'اضغط للتحدّث';
      micHint.textContent  = 'قُل سؤالك بوضوح بالعربية';
      micTimer.hidden = true;
      micBtn.setAttribute('aria-label', 'ابدأ التسجيل الصوتي');
    } else if (state === 'recording') {
      micLabel.textContent = 'أتحدّث الآن…';
      micHint.textContent  = 'اضغط على الزر مرّة أخرى للإيقاف والإرسال';
      micTimer.hidden = false;
      micBtn.setAttribute('aria-label', 'أوقف التسجيل');
    } else if (state === 'processing') {
      micLabel.textContent = 'جارٍ المعالجة…';
      micHint.textContent  = 'نُحلّل صوتك ونحوِّله إلى استعلام';
      micTimer.hidden = true;
      micBtn.setAttribute('aria-label', 'جارٍ المعالجة');
    }
  };

  // ────────────── Audio-reactive bars ──────────────
  const startVisualizer = (stream) => {
    try {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const source = audioCtx.createMediaStreamSource(stream);
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 64;
      analyser.smoothingTimeConstant = 0.7;
      source.connect(analyser);
      const data = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        analyser.getByteFrequencyData(data);
        // map 7 frequency bands to 7 bars
        const n = barEls.length;
        for (let i = 0; i < n; i++) {
          // pick bins from low → high → low (mirror for symmetry)
          const idx = Math.floor((i / (n - 1)) * (data.length - 1));
          const mirror = i < n / 2 ? idx : Math.floor(((n - 1 - i) / (n - 1)) * (data.length - 1));
          const v = data[mirror] / 255;
          const h = 8 + Math.pow(v, 0.7) * 64; // 8 → ~72 px
          barEls[i].style.height = h + 'px';
          barEls[i].style.animation = 'none';
        }
        rafId = requestAnimationFrame(tick);
      };
      tick();
    } catch {
      /* visualizer is optional; ignore failures */
    }
  };
  const stopVisualizer = () => {
    if (rafId) { cancelAnimationFrame(rafId); rafId = null; }
    if (audioCtx) { audioCtx.close().catch(() => {}); audioCtx = null; }
    barEls.forEach((b) => { b.style.height = ''; b.style.animation = ''; });
  };

  // ────────────── Recording ──────────────
  const startRecording = async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      showError('غير مدعوم', 'متصفّحك لا يدعم تسجيل الصوت.');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunks = [];
      const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : (MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : '');
      mediaRecorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      mediaRecorder.addEventListener('dataavailable', (ev) => {
        if (ev.data && ev.data.size > 0) audioChunks.push(ev.data);
      });
      mediaRecorder.addEventListener('stop', async () => {
        stream.getTracks().forEach((t) => t.stop());
        stopVisualizer();
        await handleRecordingComplete();
      });
      recordStart = Date.now();
      recordTimerId = setInterval(() => {
        micTimer.textContent = fmtTime(Date.now() - recordStart);
      }, 250);
      micTimer.textContent = '00:00';
      mediaRecorder.start();
      setMicState('recording');
      startVisualizer(stream);
      clearError();
    } catch {
      showError('تعذّر الوصول إلى الميكروفون', 'يرجى منح الإذن من إعدادات المتصفّح.');
    }
  };
  const stopRecording = () => {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop();
    if (recordTimerId) { clearInterval(recordTimerId); recordTimerId = null; }
  };
  const handleRecordingComplete = async () => {
    if (audioChunks.length === 0) { setMicState('idle'); return; }
    setMicState('processing');
    renderLoading('🎙 سؤالك الصوتي');
    try {
      const blob = new Blob(audioChunks, { type: 'audio/webm' });
      const base64 = await blobToBase64(blob);
      const body = new FormData();
      body.append('audio', base64);
      const res = await fetch('/process_audio', { method: 'POST', body });
      const data = await res.json();
      if (!res.ok || data.error) renderError(data.error || `خطأ في الخادم (${res.status})`);
      else renderResult(data);
    } catch {
      renderError('تعذّر معالجة التسجيل الصوتي.');
    } finally {
      setMicState('idle');
    }
  };
  const blobToBase64 = (blob) => new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onload = () => {
      const s = String(fr.result);
      const i = s.indexOf(',');
      resolve(i >= 0 ? s.slice(i + 1) : s);
    };
    fr.onerror = reject;
    fr.readAsDataURL(blob);
  });
  micBtn.addEventListener('click', () => {
    if (micState === 'idle') startRecording();
    else if (micState === 'recording') stopRecording();
  });
  // spacebar shortcut on the mic (focus the button + press space)
  micBtn.addEventListener('keydown', (e) => {
    if (e.code === 'Space' || e.key === ' ') {
      e.preventDefault();
      if (micState === 'idle') startRecording();
      else if (micState === 'recording') stopRecording();
    }
  });

  // ────────────── Results ──────────────
  const renderLoading = (echoInput) => {
    emptyState.hidden = true;
    results.innerHTML = `
      <div class="result-block">
        <div class="sec-head">
          <span class="sec-num">٠١</span>
          <h3 class="sec-title">ما فهمه النظام</h3>
          <span class="sec-divider"></span>
        </div>
        <div class="card understood">
          <p class="understood-text">${escapeHtml(echoInput)}</p>
        </div>
      </div>
      <div class="result-block">
        <div class="sec-head">
          <span class="sec-num">٠٢</span>
          <h3 class="sec-title">استعلام SQL</h3>
          <span class="sec-divider"></span>
        </div>
        <div class="sql-card">
          <div class="sql-head">
            <span class="sql-dots"><span></span><span></span><span></span></span>
            <span class="sql-label">QUERY · GENERATING…</span>
            <span style="width:46px"></span>
          </div>
          <pre class="sql-code"><span class="c">-- جارٍ توليد الاستعلام…</span>
<div class="skeleton skeleton-line w-90"></div>
<div class="skeleton skeleton-line w-70"></div>
<div class="skeleton skeleton-line w-50"></div></pre>
        </div>
      </div>
      <div class="result-block">
        <div class="sec-head">
          <span class="sec-num">٠٣</span>
          <h3 class="sec-title">النتيجة</h3>
          <span class="sec-divider"></span>
        </div>
        <div class="card result">
          <div class="skeleton skeleton-line w-90"></div>
          <div class="skeleton skeleton-line w-70"></div>
        </div>
      </div>
    `;
  };

  const renderError = (msg) => {
    emptyState.hidden = false;
    results.innerHTML = '';
    results.appendChild(emptyState);
    showError('حدث خطأ', msg);
  };

  const renderResult = (data) => {
    emptyState.hidden = true;
    const inputText  = data.input    ?? '';
    const sqlText    = data.sql      ?? '';
    const responseTx = data.response ?? '';
    const metadata   = data.metadata ?? {};
    const rowLimit   = Number(metadata.row_limit || 0);
    const overflow   = Boolean(metadata.overflow);
    const csvExportAvailable = Boolean(metadata.csv_export_available);

    const overflowHtml = overflow ? `
          <div class="overflow-note" role="status">
            <span>تم عرض أول ${rowLimit || 'عدد محدود من'} الصفوف فقط.</span>
            ${csvExportAvailable ? `
            <button type="button" class="btn-export" id="download-csv-btn">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="7 10 12 15 17 10"></polyline>
                <line x1="12" y1="15" x2="12" y2="3"></line>
              </svg>
              <span class="label">تنزيل CSV</span>
            </button>` : ''}
          </div>` : '';

    results.innerHTML = `
      <div class="result-block">
        <div class="sec-head">
          <span class="sec-num">٠١</span>
          <h3 class="sec-title">ما فهمه النظام</h3>
          <span class="sec-divider"></span>
        </div>
        <div class="card understood">
          <p class="understood-text">${escapeHtml(inputText) || '<em>—</em>'}</p>
        </div>
      </div>
      <div class="result-block">
        <div class="sec-head">
          <span class="sec-num">٠٢</span>
          <h3 class="sec-title">استعلام SQL</h3>
          <span class="sec-divider"></span>
        </div>
        <div class="sql-card">
          <div class="sql-head">
            <span class="sql-dots"><span></span><span></span><span></span></span>
            <span class="sql-label">QUERY · SQL</span>
            <button type="button" class="sql-copy" id="copy-btn" aria-label="نسخ الاستعلام">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
              <span id="copy-label">نسخ</span>
            </button>
          </div>
          <pre class="sql-code" id="sql-pre">${highlightSQL(sqlText)}</pre>
        </div>
      </div>
      <div class="result-block">
        <div class="sec-head">
          <span class="sec-num">٠٣</span>
          <h3 class="sec-title">النتيجة</h3>
          <span class="sec-divider"></span>
        </div>
        <div class="card result">
          <p class="result-text" id="response-text">${escapeHtml(responseTx) || '<em>لا توجد إجابة.</em>'}</p>
          ${overflowHtml}
          <div class="audio-row">
            <button type="button" class="btn-audio" id="play-btn" ${responseTx ? '' : 'disabled'}>
              <svg class="icon-play" width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>
              <svg class="icon-spinner" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
              <span class="equalizer" aria-hidden="true"><span></span><span></span><span></span><span></span></span>
              <span class="label">استمع للإجابة</span>
            </button>
            <span class="audio-meta">TEXT-TO-SPEECH · AR</span>
          </div>
        </div>
      </div>
    `;
    const copyBtn = $('copy-btn');
    const copyLabel = $('copy-label');
    copyBtn?.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(sqlText);
        copyLabel.textContent = 'تم النسخ ✓';
        setTimeout(() => (copyLabel.textContent = 'نسخ'), 1500);
      } catch {
        copyLabel.textContent = 'تعذّر النسخ';
      }
    });
    const playBtn = $('play-btn');
    playBtn?.addEventListener('click', () => playTTS(responseTx, playBtn));

    const downloadCsvBtn = $('download-csv-btn');
    downloadCsvBtn?.addEventListener('click', () => downloadCsv(downloadCsvBtn, sqlText));
  };

  const downloadCsv = async (btn, sqlQuery) => {
    if (btn.disabled) return;

    const label = btn.querySelector('.label');
    const originalLabel = label ? label.textContent : 'تنزيل CSV';
    btn.disabled = true;
    btn.classList.add('is-loading');
    if (label) label.textContent = 'جارٍ التحضير…';

    try {
      const body = new FormData();
      body.append('sql', sqlQuery);
      const res = await fetch('/export_csv', { method: 'POST', body });
      if (!res.ok) {
        let err = 'فشل تنزيل الملف.';
        const contentType = res.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
          const data = await res.json();
          err = data.error || err;
        }
        throw new Error(err);
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = 'query_results.csv';
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);

      if (label) label.textContent = 'تم التنزيل ✓';
      setTimeout(() => {
        if (label) label.textContent = originalLabel;
      }, 1500);
    } catch (error) {
      showError('فشل التصدير', error instanceof Error ? error.message : 'تعذر تنزيل ملف CSV.');
      if (label) label.textContent = originalLabel;
    } finally {
      btn.disabled = false;
      btn.classList.remove('is-loading');
    }
  };

  // ────────────── TTS ──────────────
  const playTTS = async (text, btn) => {
    if (!text || btn.disabled) return;
    const label = btn.querySelector('.label');
    if (btn.classList.contains('is-playing')) {
      ttsAudio.pause(); ttsAudio.currentTime = 0;
      btn.classList.remove('is-playing');
      label.textContent = 'استمع للإجابة';
      return;
    }
    btn.classList.add('is-loading'); btn.disabled = true;
    label.textContent = 'جارٍ التحميل…';
    try {
      const body = new FormData();
      body.append('text', text);
      const res = await fetch('/text_to_speech', { method: 'POST', body });
      if (!res.ok) throw new Error('tts-failed');
      const ctype = res.headers.get('content-type') || '';
      let url;
      if (ctype.includes('application/json')) {
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        const b64 = data.audio || data.audio_base64 || data.audio_content;
        if (!b64) throw new Error('no-audio');
        url = `data:audio/wav;base64,${b64}`;
      } else {
        const blob = await res.blob();
        url = URL.createObjectURL(blob);
      }
      ttsAudio.src = url;
      btn.classList.remove('is-loading');
      btn.classList.add('is-playing');
      btn.disabled = false;
      label.textContent = 'جارٍ التشغيل…';
      await ttsAudio.play();
    } catch {
      btn.classList.remove('is-loading', 'is-playing');
      btn.disabled = false;
      label.textContent = 'تعذّر التشغيل';
      setTimeout(() => (label.textContent = 'استمع للإجابة'), 1800);
    }
  };
  ttsAudio.addEventListener('ended', () => {
    const btn = $('play-btn'); if (!btn) return;
    btn.classList.remove('is-playing');
    btn.querySelector('.label').textContent = 'استمع للإجابة';
  });

  // ────────────── Init ──────────────
  setMicState('idle');
})();
