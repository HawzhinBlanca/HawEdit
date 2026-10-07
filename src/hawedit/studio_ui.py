"""Offline vanilla studio, with explicit unavailable and private-review boundaries."""

from __future__ import annotations

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="ckb" dir="rtl">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>HawEdit — Pro Kurdish Social Reel Studio</title>
    <style>
      @font-face {
        font-family: 'Vazirmatn';
        src: url('/assets/fonts/Vazirmatn.ttf') format('truetype');
        font-weight: 100 900;
        font-display: swap;
      }
      :root {
        color-scheme: dark;
        --bg: #111315;
        --surface: #1c2023;
        --border: #737d85;
        --text: #f5f7f8;
        --muted: #c2c8ce;
        --accent: #67dce8;
        --gold: #ffdc8a;
        --error: #ffb7af;
      }
      * {
        box-sizing: border-box;
        min-inline-size: 0;
        letter-spacing: 0;
      }
      body {
        margin: 0;
        background: var(--bg);
        color: var(--text);
        font:
          16px/1.65 'Vazirmatn',
          sans-serif;
      }
      button,
      input,
      select,
      textarea {
        font: inherit;
        max-inline-size: 100%;
      }
      button,
      select,
      input[type='file'],
      input[type='search'],
      input[type='file']::file-selector-button,
      summary,
      .action {
        min-block-size: 44px;
      }
      button,
      .action {
        border: 1px solid var(--border);
        border-radius: 6px;
        padding: 8px 16px;
        background: var(--surface);
        color: var(--text);
        cursor: pointer;
      }
      button:disabled {
        color: var(--muted);
        cursor: not-allowed;
        border-style: dashed;
      }
      button:not(:disabled):hover,
      .action:hover {
        border-color: var(--accent);
      }
      :focus-visible {
        outline: 3px solid var(--gold);
        outline-offset: 4px;
      }
      [hidden] {
        display: none !important;
      }
      h1,
      h2,
      h3,
      p {
        margin: 0;
      }
      h1 {
        font-size: 24px;
        line-height: 1.3;
      }
      h2 {
        font-size: 20px;
      }
      h3 {
        font-size: 17px;
      }
      p,
      bdi,
      option,
      dd,
      li {
        overflow-wrap: anywhere;
      }
      a {
        color: var(--accent);
      }
      header {
        border-block-end: 1px solid var(--border);
        padding: 20px 24px;
      }
      .header-inner {
        max-inline-size: 1280px;
        margin: auto;
        display: flex;
        gap: 16px;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
      }
      .brand {
        display: flex;
        align-items: baseline;
        gap: 12px;
      }
      .brand span {
        color: var(--muted);
        font-size: 14px;
      }
      #engineStatus {
        color: var(--gold);
        font-size: 14px;
      }
      main {
        max-inline-size: 1280px;
        margin: auto;
        padding: 24px;
        display: grid;
        grid-template-columns: minmax(0, 420px) minmax(0, 1fr);
        gap: 32px;
      }
      section {
        padding-block-end: 24px;
      }
      .source-column {
        border-inline-end: 1px solid var(--border);
        padding-inline-end: 28px;
      }
      .stack {
        display: grid;
        gap: 16px;
        align-content: start;
      }
      .toolbar {
        display: flex;
        gap: 12px;
        align-items: center;
        flex-wrap: wrap;
      }
      .field {
        display: grid;
        gap: 8px;
      }
      label {
        font-weight: 600;
      }
      input[type='file'] {
        inline-size: 100%;
        padding: 8px;
        border: 1px dashed var(--border);
        border-radius: 6px;
      }
      input[type='file']::file-selector-button {
        margin-inline-end: 12px;
        border: 0;
        border-radius: 4px;
        padding: 8px 12px;
        font: inherit;
        color: #102025;
        background: var(--accent);
      }
      select,
      input[type='search'],
      textarea {
        inline-size: 100%;
        color: var(--text);
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 6px;
        padding: 8px 12px;
      }
      select {
        text-overflow: ellipsis;
      }
      textarea {
        resize: vertical;
      }
      .primary {
        color: #102025;
        background: var(--accent);
        font-weight: 700;
      }
      .primary:disabled {
        background: var(--surface);
        color: var(--muted);
      }
      .muted {
        color: var(--muted);
        font-size: 14px;
      }
      .error {
        color: var(--error);
        font-size: 14px;
        white-space: pre-line;
      }
      .warning {
        color: var(--gold);
        font-size: 14px;
      }
      .rule {
        border-block-start: 1px solid var(--border);
        padding-block-start: 20px;
      }
      details {
        border-block: 1px solid var(--border);
        padding-block: 8px;
      }
      summary {
        cursor: pointer;
        font-weight: 600;
        padding-block: 8px;
      }
      fieldset {
        border: 0;
        padding: 16px 0 8px;
        margin: 0;
      }
      .settings-grid {
        display: grid;
        grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
        gap: 16px;
      }
      .checkbox {
        display: flex;
        gap: 12px;
        align-items: center;
        min-block-size: 44px;
        font-size: 14px;
      }
      input[type='checkbox'] {
        inline-size: 22px;
        block-size: 22px;
        flex: none;
        accent-color: var(--accent);
      }
      progress {
        inline-size: 100%;
        block-size: 12px;
        accent-color: var(--accent);
      }
      #jobSelect {
        flex: 1 1 240px;
      }
      #jobContext {
        border-inline-start: 3px solid var(--gold);
        padding-inline-start: 14px;
      }
      .candidate-list {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(min(100%, 180px), 1fr));
        gap: 12px;
      }
      .candidate {
        text-align: start;
        overflow-wrap: anywhere;
      }
      .candidate[aria-pressed='true'] {
        border-color: var(--accent);
        background: #253237;
      }
      .player-area {
        display: grid;
        grid-template-columns: minmax(0, 250px) minmax(0, 1fr);
        gap: 24px;
      }
      video {
        inline-size: 100%;
        aspect-ratio: 9/16;
        object-fit: contain;
        background: #000;
        border-radius: 4px;
      }
      dl {
        margin: 0;
        display: grid;
        grid-template-columns: minmax(0, 1fr) minmax(0, 1.5fr);
        gap: 8px 16px;
        font-size: 14px;
      }
      dt {
        color: var(--muted);
      }
      dd {
        margin: 0;
      }
      #historyDiagnostics,
      #stageList {
        margin: 0;
        padding: 0;
        list-style-position: inside;
      }
      #stageList li {
        padding-block: 4px;
      }
      .skip-link {
        position: absolute;
        inset-block-start: -200px;
        inset-inline-start: 16px;
        background: var(--surface);
        padding: 12px;
      }
      .skip-link:focus {
        inset-block-start: 12px;
        z-index: 10;
      }
      @media (max-width: 860px) {
        main {
          grid-template-columns: minmax(0, 1fr);
          gap: 24px;
        }
        .source-column {
          border-inline-end: 0;
          padding-inline-end: 0;
          border-block-end: 1px solid var(--border);
        }
      }
      @media (max-width: 520px) {
        header,
        main {
          padding: 16px;
        }
        .settings-grid,
        .player-area {
          grid-template-columns: minmax(0, 1fr);
        }
        video {
          max-inline-size: 250px;
          justify-self: center;
        }
        .toolbar > button {
          flex: 1 1 120px;
        }
        dl {
          grid-template-columns: minmax(0, 1fr);
          gap: 4px;
        }
        dd {
          margin-block-end: 8px;
        }
      }
      @media (prefers-reduced-motion: reduce) {
        * {
          scroll-behavior: auto;
        }
      }
    </style>
  </head>
  <body>
    <a class="skip-link" href="#studio">بڕۆ بۆ ستۆدیۆ</a>
    <header>
      <div class="header-inner">
        <div class="brand">
          <h1 dir="ltr">HawEdit</h1>
          <span>ستۆدیۆی شۆرت</span>
        </div>
        <p id="engineStatus" role="status" aria-live="polite">پشکنینی ئامادەیی…</p>
      </div>
    </header>
    <main id="studio" tabindex="-1">
      <section class="source-column stack" aria-labelledby="sourceHeading">
        <h2 id="sourceHeading">ڤیدیۆی سەرچاوە</h2>
        <div class="field">
          <label for="videoFile">فایلی ڤیدیۆ هەڵبژێرە</label>
          <input
            type="file"
            id="videoFile"
            accept=".mp4,.mov,.mkv,.avi,.webm,.ts,.m4v"
            aria-describedby="fileInfo sourceError"
          />
          <p id="fileInfo" class="muted" dir="auto">هیچ فایلێک هەڵنەبژێردراوە.</p>
        </div>
        <div class="toolbar">
          <button id="uploadBtn" type="button" disabled>بارکردنی ڤیدیۆ</button>
          <button id="recoverUploadBtn" type="button" hidden>پشکنینی بارکردن</button>
        </div>
        <progress
          id="uploadProgress"
          aria-label="پێشکەوتنی بارکردنی بایتەکان"
          hidden
        ></progress>
        <p id="uploadMessage" role="status" aria-live="polite" class="muted"></p>
        <p id="sourceError" role="alert" class="error" hidden></p>
        <details id="advancedSettings">
          <summary>ڕێکخستنی پێشکەوتوو</summary>
          <fieldset id="settingsFields">
            <div class="settings-grid">
              <div class="field">
                <label for="optPreset">شێواز</label>
                <select id="optPreset">
                  <option value="viral">ڤایرۆڵ</option>
                  <option value="broadcast">برۆدکاست</option>
                  <option value="split">دووانە</option>
                </select>
              </div>
              <div class="field">
                <label for="optCaptionStyle">ژێرنووس</label>
                <select id="optCaptionStyle">
                  <option value="">بەپێی شێواز</option>
                  <option value="kinetic_pop">جووڵەی وشەکان</option>
                  <option value="viral_popup">دەرکەوتنی وشە</option>
                  <option value="rtl_highlight">دیاریکردنی وشە</option>
                  <option value="broadcast_studio">تەواوی دێڕ</option>
                </select>
              </div>
              <div class="field">
                <label for="optMaxClips">ژمارەی بڕگەکان</label>
                <select id="optMaxClips">
                  <option value="1">١</option>
                  <option value="2">٢</option>
                  <option value="3" selected>٣</option>
                  <option value="5">٥</option>
                </select>
              </div>
              <div class="field">
                <label for="optScreener">فلتەری سەرەتایی</label>
                <select id="optScreener">
                  <option value="none">بێ فلتەری زیادە</option>
                  <option value="gemini-flash" disabled>
                    Gemini Flash — ئامادە نییە
                  </option>
                  <option value="jev" disabled>Jev — ئامادە نییە</option>
                </select>
              </div>
            </div>
            <label class="checkbox">
              <input id="optHookBanner" type="checkbox" checked />
              ناونیشانی دەستپێک
            </label>
            <label class="checkbox">
              <input id="optSilence" type="checkbox" checked />
              کەمکردنەوەی بێدەنگی
            </label>
          </fieldset>
        </details>
        <button
          id="startBtn"
          type="button"
          class="primary"
          disabled
          aria-describedby="generationReason"
        >
          دروستکردنی بڕگەکان
        </button>
        <p id="generationReason" class="warning">دروستکردن هێشتا ئامادە نییە.</p>
        <p id="storageError" role="alert" class="error" hidden></p>
        <p class="muted" id="sourceIdentity" dir="auto"></p>
      </section>
      <div class="stack">
        <section class="stack" aria-labelledby="historyHeading">
          <h2 id="historyHeading">کارەکان</h2>
          <div class="field">
            <label for="historySearch">گەڕان لە کارەکان</label>
            <input
              id="historySearch"
              type="search"
              dir="auto"
              aria-controls="jobSelect"
              autocomplete="off"
              disabled
            />
          </div>
          <div class="field">
            <label for="jobSelect">کاری هەڵبژێردراو</label>
            <div class="toolbar">
              <select id="jobSelect">
                <option value="">کارێک هەڵبژێرە</option>
              </select>
              <button id="refreshBtn" type="button">نوێکردنەوە</button>
            </div>
          </div>
          <p id="historyMessage" role="status" aria-live="polite" class="muted">
            پشکنینی مێژووی کارەکان…
          </p>
          <p id="historySelectionWarning" aria-live="polite" class="warning" hidden></p>
          <ul id="historyDiagnostics" class="error" hidden></ul>
          <div id="jobContext" class="stack" hidden>
            <h3 id="jobTitle"></h3>
            <p id="jobIdentity" class="muted" dir="auto"></p>
            <p id="jobMessage" aria-live="polite" class="warning"></p>
          </div>
          <p id="jobError" role="alert" class="error" hidden></p>
        </section>
        <section class="stack rule" aria-labelledby="candidatesHeading">
          <h2 id="candidatesHeading">بڕگەکان</h2>
          <p id="candidateMessage" class="muted">هیچ کارێک هەڵنەبژێردراوە.</p>
          <div
            id="clipTabs"
            class="candidate-list"
            role="group"
            aria-label="بڕگەی هەڵبژێردراو"
          ></div>
          <div id="previewPanel" class="stack" hidden>
            <h3 id="headlineText" dir="auto"></h3>
            <p class="warning">پێشبینینی تایبەت؛ بۆ بڵاوکردنەوە پشتڕاست نەکراوەتەوە.</p>
            <div class="player-area">
              <video
                id="player"
                controls
                playsinline
                preload="metadata"
                hidden
                aria-label="پێشبینینی بڕگە"
              ></video>
              <div class="stack">
                <p
                  id="previewStatus"
                  role="status"
                  aria-live="polite"
                  class="muted"
                ></p>
                <p id="previewError" role="alert" class="error" hidden></p>
                <button id="retryPreviewBtn" type="button" hidden>
                  دووبارە پشکنینی پێشبینین
                </button>
                <dl>
                  <dt>ماوەی پێوانەکراو</dt>
                  <dd id="measuredDuration">نەزانراو</dd>
                  <dt>هەڵسەنگاندنی ناوەڕۆک</dt>
                  <dd id="qualityScore">نەزانراو</dd>
                  <dt>ماوەی پلەیەر</dt>
                  <dd id="playerDuration">نەزانراو</dd>
                </dl>
                <a id="privateCopy" class="action" hidden>داگرتنی کۆپی تایبەت</a>
              </div>
            </div>
          </div>
        </section>
        <section class="stack rule" aria-labelledby="stagesHeading">
          <h2 id="stagesHeading">قۆناغەکان</h2>
          <p id="stageMessage" class="muted">هیچ قۆناغێکی پشتڕاستکراو نییە.</p>
          <progress
            id="stageProgress"
            aria-label="قۆناغە تەواوبووە بینراوەکان"
            hidden
          ></progress>
          <ol id="stageList"></ol>
        </section>
        <section class="stack rule" aria-labelledby="reviewHeading">
          <h2 id="reviewHeading">پێداچوونەوە و دەرکردن</h2>
          <div class="toolbar">
            <button id="reviseBtn" type="button" disabled>دەستکاریکردن</button>
            <button id="approveBtn" type="button" disabled>پەسەندکردن</button>
            <button id="exportBtn" type="button" disabled>دەرکردنی پشتڕاستکراو</button>
          </div>
          <p class="warning">
            دەستکاریی ڕێندەرکراو، پەسەندکردنی واژۆکراو و دەرکردنی پشتڕاستکراو هێشتا
            بەستراوەتەوە نییە.
          </p>
        </section>
      </div>
    </main>
    <noscript>بۆ کارکردنی ستۆدیۆ جاڤاسکریپت پێویستە.</noscript>
    <script>
      'use strict';
      const $ = (id) => document.getElementById(id);
      const unknown = 'نەزانراو';
      const sourceIdPattern = /^[a-f0-9]{32}$/;
      const state = {
        file: null,
        source: null,
        ticket: null,
        request: null,
        requestUncertain: false,
        uploadUncertain: false,
        busy: false,
        runnerReady: false,
        storageReady: true,
        job: null,
        clip: null,
        selectionEpoch: 0,
        previewEpoch: 0,
        historyEpoch: 0,
        historyJobs: [],
        historySelected: '',
        historyLoaded: false,
        historyTruncated: false,
        readinessEpoch: 0,
        previewController: null,
      };
      const statusLabels = {
        queued: 'لە ڕیزدایە',
        running: 'لە کاردایە',
        'awaiting-review': 'چاوەڕوانی پێداچوونەوە',
        'partially-completed': 'بەشێکی تەواو بووە',
        completed: 'بڵاوکردنەوەی پشتڕاستکراو',
        interrupted: 'پچڕاو؛ پێویستی بە گەڕاندنەوە هەیە',
        failed: 'شکستی هێنا',
        cancelled: 'هەڵوەشێنراوە',
        'unverified-historical': 'کاری کۆن — پشتڕاست نەکراوەتەوە',
      };

      function message(id, text) {
        $(id).textContent = text || '';
        $(id).hidden = !text;
      }
      function save(key, value) {
        try {
          if (value === null) localStorage.removeItem('hawedit.studio.v1.' + key);
          else localStorage.setItem('hawedit.studio.v1.' + key, JSON.stringify(value));
          return true;
        } catch (error) {
          state.storageReady = false;
          message(
            'storageError',
            'پاشەکەوتکردنی ناسنامەی داواکاری لە وێبگەڕ شکستی هێنا؛ داواکاریی نوێ نانێردرێت.',
          );
          return false;
        }
      }
      function read(key) {
        try {
          const raw = localStorage.getItem('hawedit.studio.v1.' + key);
          if (raw && raw.length > 16384) throw new Error('oversized browser record');
          return raw ? JSON.parse(raw) : null;
        } catch (error) {
          state.storageReady = false;
          message(
            'storageError',
            'تۆماری وێبگەڕ نەتوانرا بخوێندرێتەوە؛ ناسنامەی داواکاری پشتڕاست بکەرەوە.',
          );
          return null;
        }
      }
      function validSource(value) {
        return (
          value && typeof value === 'object' && !Array.isArray(value) &&
          typeof value.source_id === 'string' &&
          typeof value.sha256 === 'string' &&
          sourceIdPattern.test(value.source_id) &&
          /^[a-f0-9]{64}$/.test(value.sha256) &&
          Number.isSafeInteger(value.size) &&
          value.size > 0 &&
          typeof value.filename === 'string' && value.filename.length <= 240 &&
          Number.isSafeInteger(value.duration_ms) &&
          value.duration_ms > 0
        );
      }
      function controls() {
        const locked = state.busy || state.requestUncertain;
        $('videoFile').disabled = locked || state.uploadUncertain;
        $('settingsFields').disabled = locked;
        $('uploadBtn').disabled =
          locked || !state.file || Boolean(state.source) ||
          state.uploadUncertain || !state.storageReady;
        $('recoverUploadBtn').hidden = !state.ticket;
        $('recoverUploadBtn').disabled = state.busy;
        $('startBtn').disabled =
          state.busy ||
          !state.storageReady ||
          !state.source ||
          (!state.runnerReady && !state.requestUncertain) ||
          state.uploadUncertain;
        $('startBtn').textContent = state.requestUncertain
          ? 'پشکنینی هەمان داواکاری'
          : 'دروستکردنی بڕگەکان';
      }
      async function api(path, options = {}) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 30000);
        try {
          const response = await fetch(path, {
            ...options,
            signal: controller.signal,
            cache: 'no-store',
          });
          const data = await response.json();
          if (!response.ok) {
            const error = new Error(data.error || 'HTTP ' + response.status);
            error.status = response.status;
            error.code = data.code;
            error.data = data;
            throw error;
          }
          return data;
        } finally {
          clearTimeout(timer);
        }
      }
      function showSource(source) {
        if (!validSource(source))
          throw new Error('ناسنامەی سەرچاوە پشتڕاست نەکراوەتەوە.');
        if (!save('source', source))
          throw new Error('ناسنامەی سەرچاوە پاشەکەوت نەکرا.');
        state.source = source;
        state.uploadUncertain = false;
        message('fileInfo', source.filename + ' · ' + source.size + ' bytes');
        message('sourceIdentity', source.filename + ' · ' + source.source_id);
        message('uploadMessage', 'بارکردن و پشکنینی ڤیدیۆ تەواو بووە.');
        $('uploadProgress').hidden = true;
        controls();
      }
      function transfer(file, uploadId) {
        return new Promise((resolve, reject) => {
          const xhr = new XMLHttpRequest();
          xhr.upload.addEventListener('progress', (event) => {
            if (event.lengthComputable) {
              $('uploadProgress').max = event.total;
              $('uploadProgress').value = event.loaded;
              message(
                'uploadMessage',
                'بارکردنی بایتەکان: ' +
                  Math.floor((event.loaded * 100) / event.total) +
                  '%',
              );
            }
          });
          xhr.upload.addEventListener('load', () => {
            $('uploadProgress').removeAttribute('value');
            message('uploadMessage', 'بایتەکان نێردران؛ چاوەڕوانی پشکنینی ڤیدیۆ…');
          });
          xhr.open('PUT', '/api/uploads/' + encodeURIComponent(uploadId));
          xhr.timeout = 24 * 60 * 60 * 1000;
          xhr.setRequestHeader('Content-Type', 'application/octet-stream');
          xhr.addEventListener('load', () => {
            try {
              const result = JSON.parse(xhr.responseText);
              if (xhr.status < 200 || xhr.status >= 300)
                throw new Error(result.error || 'HTTP ' + xhr.status);
              resolve(result);
            } catch (error) {
              reject(error);
            }
          });
          for (const event of ['error', 'abort', 'timeout'])
            xhr.addEventListener(event, () =>
              reject(new Error('دۆخی بارکردن نەزانراوە؛ پشکنینی بارکردن هەڵبژێرە.')),
            );
          xhr.send(file);
        });
      }
      async function upload() {
        const file = state.file;
        if (!file || state.busy || state.uploadUncertain || state.requestUncertain)
          return;
        state.busy = true;
        state.source = null;
        state.ticket = null;
        if (!save('source', null) || !save('upload', null)) {
          state.busy = false;
          controls();
          return;
        }
        controls();
        message('sourceError', '');
        message('sourceIdentity', '');
        $('uploadProgress').hidden = false;
        $('uploadProgress').removeAttribute('value');
        message('uploadMessage', 'ئامادەکردنی بارکردن…');
        try {
          const ticket = await api('/api/uploads', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename: file.name, size: file.size }),
          });
          if (
            !ticket ||
            !sourceIdPattern.test(ticket.upload_id) ||
            ticket.size !== file.size
          )
            throw new Error('ناسنامەی بارکردن نادروستە.');
          state.ticket = ticket;
          if (!save('upload', ticket))
            throw new Error('ناسنامەی بارکردن پاشەکەوت نەکرا؛ هیچ بایتێک نەنێردرا.');
          state.uploadUncertain = true;
          const source = await transfer(file, ticket.upload_id);
          if (source.source_id !== ticket.upload_id || source.size !== file.size)
            throw new Error('وەڵامی بارکردن لەگەڵ فایلەکە ناگونجێت.');
          showSource(source);
        } catch (error) {
          message('sourceError', error.message);
          message(
            'uploadMessage',
            state.uploadUncertain
              ? 'ئەنجامی بارکردن پشتڕاست بکەرەوە پێش دووبارە ناردن.'
              : 'بارکردن تەواو نەبوو.',
          );
          $('uploadProgress').hidden = true;
        } finally {
          state.busy = false;
          controls();
        }
      }
      async function recoverUpload() {
        if (!state.ticket || state.busy) return;
        state.busy = true;
        controls();
        message('sourceError', '');
        try {
          const result = await api(
            '/api/uploads/' + encodeURIComponent(state.ticket.upload_id),
          );
          if (result.upload_id !== state.ticket.upload_id)
            throw new Error('ناسنامەی گەڕاندنەوە ناگونجێت.');
          if (result.state === 'ready') {
            if (
              !validSource(result.source) ||
              result.source.source_id !== state.ticket.upload_id
            )
              throw new Error('سەرچاوەی گەڕێندراوە پشتڕاست نەکراوەتەوە.');
            showSource(result.source);
          } else if (
            ['reserved', 'failed', 'expired', 'interrupted'].includes(result.state)
          ) {
            state.uploadUncertain = false;
            state.ticket = null;
            if (!save('upload', null))
              throw new Error('ناسنامەی گەڕاندنەوە پاشەکەوت نەکرا.');
            message(
              'uploadMessage',
              'بارکردن تەواو نەبوو؛ فایل هەڵبژێرە و دووبارە بار بکە.',
            );
            if (result.error) message('sourceError', result.error);
          } else {
            state.uploadUncertain = true;
            message(
              'uploadMessage',
              'بارکردن هێشتا لە کاردایە؛ هیچ بارکردنێکی دووبارە نانێردرێت.',
            );
          }
        } catch (error) {
          state.uploadUncertain = true;
          message('sourceError', error.message);
        } finally {
          state.busy = false;
          controls();
        }
      }
      function options() {
        const result = {
          preset: $('optPreset').value,
          max_clips: Number($('optMaxClips').value),
          screener: $('optScreener').value,
          hook_banner: $('optHookBanner').checked,
          silence_tightening: $('optSilence').checked,
        };
        if ($('optCaptionStyle').value)
          result.caption_style = $('optCaptionStyle').value;
        return result;
      }
      function validOptions(value) {
        const keys = ['preset', 'max_clips', 'screener', 'hook_banner',
          'silence_tightening', 'caption_style'];
        return value && typeof value === 'object' && !Array.isArray(value) &&
          Object.keys(value).every(key => keys.includes(key)) &&
          ['viral', 'broadcast', 'split'].includes(value.preset) &&
          [1, 2, 3, 5].includes(value.max_clips) && value.screener === 'none' &&
          typeof value.hook_banner === 'boolean' &&
          typeof value.silence_tightening === 'boolean' &&
          (value.caption_style === undefined ||
            ['kinetic_pop', 'viral_popup', 'rtl_highlight',
              'broadcast_studio'].includes(value.caption_style));
      }
      function applyOptions(value) {
        if (!validOptions(value)) {
          state.storageReady = false;
          message('storageError', 'ڕێکخستنی پاشەکەوتکراو نادروست یان ئامادە نییە.');
          return;
        }
        $('optPreset').value = value.preset;
        $('optCaptionStyle').value = value.caption_style || '';
        $('optMaxClips').value = String(value.max_clips);
        $('optScreener').value = value.screener;
        $('optHookBanner').checked = value.hook_banner;
        $('optSilence').checked = value.silence_tightening;
      }
      async function generate() {
        if (state.busy || !state.source || !state.storageReady) return;
        if (!state.runnerReady && !state.requestUncertain) return;
        message('sourceError', '');
        if (!state.request)
          state.request = {
            schema: 1,
            source_id: state.source.source_id,
            client_token: crypto.randomUUID(),
            options: options(),
          };
        if (!save('request', state.request)) {
          controls();
          return;
        }
        state.requestUncertain = true;
        state.busy = true;
        controls();
        try {
          const job = await api('/api/repurpose', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(state.request),
          });
          if (!job || typeof job.job_id !== 'string' || !job.job_id)
            throw new Error('ئەنجامی داواکاری نادیارە؛ هەمان ناسنامە پشکنین بکە.');
          if (!save('selected', job.job_id) || !save('request', null))
            throw new Error('ناسنامەی کاری وەرگیراو پاشەکەوت نەکرا.');
          state.request = null;
          state.requestUncertain = false;
          await refreshHistory(job.job_id);
        } catch (error) {
          if (error.status === 400 || error.code === 'studio_runner_unavailable') {
            if (save('request', null)) {
              state.request = null;
              state.requestUncertain = false;
            }
          }
          message('sourceError', error.message);
        } finally {
          state.busy = false;
          controls();
        }
      }
      function clearPreview() {
        state.previewEpoch++;
        if (state.previewController) state.previewController.abort();
        state.previewController = null;
        state.clip = null;
        const player = $('player');
        player.pause();
        player.removeAttribute('src');
        player.removeAttribute('poster');
        player.load();
        player.hidden = true;
        $('previewPanel').hidden = true;
        $('privateCopy').hidden = true;
        $('privateCopy').removeAttribute('href');
        $('privateCopy').removeAttribute('download');
        $('retryPreviewBtn').hidden = true;
        for (const id of ['measuredDuration', 'qualityScore', 'playerDuration'])
          $(id).textContent = unknown;
        message('previewError', '');
        message('previewStatus', '');
      }
      function clearJob() {
        state.job = null;
        clearPreview();
        $('clipTabs').replaceChildren();
        $('jobContext').hidden = true;
        $('stageList').replaceChildren();
        $('stageProgress').hidden = true;
        message('jobError', '');
        message('stageMessage', 'هیچ قۆناغێکی پشتڕاستکراو نییە.');
        message('candidateMessage', 'هیچ کارێک هەڵنەبژێردراوە.');
      }
      function diagnostics(id, rows) {
        const list = $(id);
        list.replaceChildren();
        list.hidden = !Array.isArray(rows) || !rows.length;
        if (Array.isArray(rows))
          for (const row of rows) {
            const item = document.createElement('li');
            item.textContent =
              (row.code || '') + ': ' + (row.message || 'تۆماری نادروست');
            item.dir = 'auto';
            list.append(item);
          }
      }
      function stages(job) {
        const rows = Array.isArray(job.stages) ? job.stages : [];
        $('stageList').replaceChildren();
        $('stageProgress').hidden = true;
        if (!rows.length) {
          message('stageMessage', 'هیچ قۆناغێکی پشتڕاستکراو نییە.');
          return;
        }
        const labels = {
          started: 'لە کاردایە',
          completed: 'تەواو بوو',
          skipped: 'تێپەڕێنرا',
          failed: 'شکستی هێنا',
          refused: 'ڕەت کرایەوە',
        };
        for (const row of rows) {
          const item = document.createElement('li');
          item.dir = 'auto';
          item.textContent =
            (row.stage || unknown) + ' · ' + (labels[row.state] || unknown);
          $('stageList').append(item);
        }
        const finished = rows.filter((row) =>
          ['completed', 'skipped'].includes(row.state),
        ).length;
        message(
          'stageMessage',
          'قۆناغە بینراوەکان: ' +
            finished +
            ' / ' +
            rows.length +
            '؛ پێشکەوتنی ناو قۆناغ نەزانراوە.',
        );
        $('stageProgress').max = rows.length;
        $('stageProgress').value = finished;
        $('stageProgress').hidden = false;
      }
      async function selectJob(jobId) {
        const epoch = ++state.selectionEpoch;
        clearJob();
        if (!save('selected', jobId || null)) controls();
        if (!jobId) return;
        message('candidateMessage', 'خوێندنەوەی کاری هەڵبژێردراو…');
        try {
          const job = await api('/api/jobs/' + encodeURIComponent(jobId));
          if (epoch !== state.selectionEpoch) return;
          if (job.job_id !== jobId) throw new Error('ناسنامەی کار ناگونجێت.');
          state.job = job;
          $('jobContext').hidden = false;
          $('jobTitle').textContent = job.source || job.headline || jobId;
          $('jobIdentity').textContent =
            jobId + ' · ' + recordedDate(job.created_at);
          let label = statusLabels[job.status] || unknown;
          if (job.status === 'completed' && job.publication_verified !== true)
            label = statusLabels['unverified-historical'];
          message(
            'jobMessage',
            (job.historical ? 'مێژووی کار · ' : '') +
              label +
              (job.recovery_required ? ' · دووبارە خۆکارانە نانێردرێت.' : ''),
          );
          message('jobError', job.error || '');
          stages(job);
          const clips = Array.isArray(job.clips) ? job.clips : [];
          message(
            'candidateMessage',
            clips.length
              ? clips.length + ' بڕگە؛ هیچ پەسەندکردنێک لە ڕیزبەندییەوە ناگیرێت.'
              : 'هیچ بڕگەیەکی تۆمارکراو نییە.',
          );
          if (Array.isArray(job.diagnostics) && job.diagnostics.length)
            message('jobError', job.diagnostics.map((row) => row.message).join('\n'));
          for (const [index, clip] of clips.entries()) {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'candidate';
            button.dir = 'auto';
            button.setAttribute('aria-pressed', 'false');
            button.textContent = index + 1 + ' · ' + (clip.headline || clip.clip_id);
            button.addEventListener('click', () => selectClip(clip, button));
            $('clipTabs').append(button);
          }
        } catch (error) {
          if (epoch !== state.selectionEpoch) return;
          message('jobError', error.message);
          message('candidateMessage', 'کاری هەڵبژێردراو نەتوانرا بخوێندرێتەوە.');
        }
      }
      async function selectClip(clip, button) {
        clearPreview();
        state.clip = clip;
        const epoch = state.previewEpoch;
        const jobId = state.job.job_id;
        for (const item of $('clipTabs').children)
          item.setAttribute('aria-pressed', String(item === button));
        $('previewPanel').hidden = false;
        $('headlineText').textContent = clip.headline || clip.clip_id;
        if (
          Number.isFinite(clip.duration_s) &&
          clip.duration_s > 0 &&
          clip.preview_verified === true
        )
          $('measuredDuration').textContent = clip.duration_s + ' چرکە';
        if (Number.isFinite(clip.hook_score))
          $('qualityScore').textContent = String(clip.hook_score);
        const path =
          '/api/jobs/' +
          encodeURIComponent(jobId) +
          '/clips/' +
          encodeURIComponent(clip.clip_id) +
          '/preview';
        message('previewStatus', 'پشکنینی بایتەکانی پێشبینینی تایبەت…');
        const controller = new AbortController();
        state.previewController = controller;
        const timer = setTimeout(() => controller.abort(), 60000);
        try {
          const response = await fetch(path, {
            method: 'HEAD',
            cache: 'no-store',
            signal: controller.signal,
          });
          if (epoch !== state.previewEpoch) return;
          if (
            !response.ok ||
            response.headers.get('X-HawEdit-Artifact-State') !== 'private-preview' ||
            response.headers.get('Content-Type') !== 'video/mp4' ||
            !/^"[a-f0-9]{64}"$/.test(response.headers.get('ETag') || '')
          )
            throw new Error('پێشبینین ڕەت کرایەوە: HTTP ' + response.status);
          const player = $('player');
          player.src = path;
          player.hidden = false;
          player.load();
          const link = $('privateCopy');
          link.href = path;
          link.download = clip.clip_id + '-private.mp4';
          link.hidden = false;
          message('previewStatus', 'پێشبینینی تایبەت؛ پەسەندکردنی بڵاوکردنەوە نییە.');
        } catch (error) {
          if (epoch !== state.previewEpoch) return;
          message('previewError', error.message);
          message('previewStatus', 'پێشبینین ئامادە نییە.');
          $('retryPreviewBtn').hidden = false;
        } finally {
          clearTimeout(timer);
        }
      }
      function recordedDate(value) {
        if (typeof value !== 'number' || !Number.isFinite(value) || value < 0)
          return unknown;
        const date = new Date(value * 1000);
        if (!Number.isFinite(date.getTime())) return unknown;
        return date.toLocaleString('ckb');
      }
      function renderHistory(selected = state.historySelected) {
        const normalize = (value) => value.normalize('NFKC').toLocaleLowerCase('ckb');
        const query = normalize($('historySearch').value.trim());
        const matched = state.historyJobs.filter((job) =>
          normalize(job.job_id + ' ' + (job.source || '')).includes(query),
        );
        const matches = new Set(matched.map((job) => job.job_id));
        const selectedOutside = Boolean(selected) && !matches.has(selected) &&
          state.historyJobs.some((job) => job.job_id === selected);
        const select = $('jobSelect');
        select.replaceChildren();
        const empty = document.createElement('option');
        empty.value = '';
        empty.textContent = 'کارێک هەڵبژێرە';
        select.append(empty);
        const isolate = (value) => '\u2068' + value + '\u2069';
        for (const job of state.historyJobs) {
          if (!matches.has(job.job_id) && job.job_id !== selected) continue;
          const item = document.createElement('option');
          item.value = job.job_id;
          item.dir = 'auto';
          let label = statusLabels[job.status] || unknown;
          if (job.status === 'completed' && job.publication_verified !== true)
            label = statusLabels['unverified-historical'];
          item.textContent = [
            job.job_id,
            recordedDate(job.created_at),
            job.source || unknown,
            label,
          ].map(isolate).join(' · ');
          select.append(item);
        }
        state.historySelected = selected;
        select.value = selected;
        $('historySearch').disabled = !state.historyLoaded;
        message('historySelectionWarning', selectedOutside
          ? 'کاری هەڵبژێردراو لە ئەنجامی گەڕاندا نییە؛ هەڵبژاردنەکە پارێزراوە.'
          : '');
        message('historyMessage', state.historyLoaded
          ? '\u2066' + matched.length + ' / ' + state.historyJobs.length + '\u2069' +
            ' کار؛ هیچ بڵاوکردنەوەیەک پشتڕاست نەکراوەتەوە.' +
            (state.historyTruncated ? ' هەموو مێژوو نیشان نەدراوە.' : '')
          : 'مێژووی کارەکان ئامادە نییە؛ لیستی بەتاڵ ئەنجامی پشتڕاستکراو نییە.');
      }
      async function refreshHistory(selected = state.historySelected) {
        const epoch = ++state.historyEpoch;
        const selectionEpoch = state.selectionEpoch;
        $('refreshBtn').disabled = true;
        try {
          const history = await api('/api/history');
          if (epoch !== state.historyEpoch) return;
          if (selectionEpoch !== state.selectionEpoch) selected = $('jobSelect').value;
          if (history.schema !== 1 || !Array.isArray(history.jobs))
            throw new Error('تۆماری مێژوو نادروستە.');
          state.historyJobs = history.jobs;
          state.historyLoaded = true;
          state.historyTruncated = history.truncated === true;
          renderHistory(selected);
          const select = $('jobSelect');
          diagnostics('historyDiagnostics', history.diagnostics);
          if (selected) {
            select.value = selected;
            if (select.value !== selected) {
              ++state.selectionEpoch;
              clearJob();
              message(
                'jobError',
                'کاری هەڵبژێردراو لە مێژووی بینراودا نییە؛ ناسنامەکە پارێزراوە.',
              );
            } else await selectJob(selected);
          }
        } catch (error) {
          if (epoch !== state.historyEpoch) return;
          state.historyJobs = [];
          state.historyLoaded = false;
          renderHistory(state.historySelected);
          if (selectionEpoch === state.selectionEpoch) {
            ++state.selectionEpoch;
            clearJob();
            message('jobError', error.message);
          }
          diagnostics('historyDiagnostics', error.data && error.data.diagnostics);
          message(
            'historyMessage',
            'مێژووی کارەکان ئامادە نییە؛ لیستی بەتاڵ ئەنجامی پشتڕاستکراو نییە.',
          );
        } finally {
          if (epoch === state.historyEpoch) $('refreshBtn').disabled = false;
        }
      }
      async function readiness() {
        const epoch = ++state.readinessEpoch;
        state.runnerReady = false;
        controls();
        try {
          const result = await api('/api/status');
          if (epoch !== state.readinessEpoch) return;
          state.runnerReady = result.runner_ready === true;
          message(
            'engineStatus',
            state.runnerReady ? 'ئامادەی دروستکردن' : 'دروستکردن ئامادە نییە',
          );
          message(
            'generationReason',
            state.runnerReady
              ? state.source
                ? ''
                : 'سەرەتا ڤیدیۆیەک بار بکە.'
              : 'کارکەری پارێزراوی ستۆدیۆ و ڕێکخستنی مۆدێلەکان هێشتا نەبەستراونەتەوە.',
          );
        } catch (error) {
          if (epoch !== state.readinessEpoch) return;
          message('engineStatus', 'ئامادەیی نەزانراوە');
          message('generationReason', 'پشکنینی کارکەر شکستی هێنا: ' + error.message);
        } finally {
          controls();
        }
      }
      $('videoFile').addEventListener('change', () => {
        state.file = $('videoFile').files[0] || null;
        state.source = null;
        state.ticket = null;
        save('source', null);
        save('upload', null);
        message('sourceIdentity', '');
        message('sourceError', '');
        message('uploadMessage', '');
        $('uploadProgress').hidden = true;
        $('uploadProgress').removeAttribute('value');
        message(
          'fileInfo',
          state.file
            ? state.file.name + ' · ' + state.file.size + ' bytes'
            : 'هیچ فایلێک هەڵنەبژێردراوە.',
        );
        controls();
      });
      $('uploadBtn').addEventListener('click', upload);
      $('recoverUploadBtn').addEventListener('click', recoverUpload);
      $('startBtn').addEventListener('click', generate);
      $('settingsFields').addEventListener('change', () => {
        save('options', options()); controls();
      });
      $('historySearch').addEventListener('input', () => renderHistory());
      $('jobSelect').addEventListener('change', () => {
        state.historySelected = $('jobSelect').value;
        renderHistory();
        selectJob(state.historySelected);
      });
      $('refreshBtn').addEventListener('click', async () => {
        await readiness();
        await refreshHistory();
      });
      $('retryPreviewBtn').addEventListener('click', () => {
        if (state.clip)
          selectClip(
            state.clip,
            Array.from($('clipTabs').children).find(
              (item) => item.getAttribute('aria-pressed') === 'true',
            ),
          );
      });
      $('player').addEventListener('loadedmetadata', () => {
        if (!state.clip || !$('player').hasAttribute('src')) return;
        const duration = $('player').duration;
        $('playerDuration').textContent =
          Number.isFinite(duration) && duration > 0
            ? duration.toFixed(1) + ' چرکە'
            : unknown;
      });
      $('player').addEventListener('error', () => {
        if (!state.clip || !$('player').hasAttribute('src')) return;
        $('player').hidden = true;
        $('privateCopy').hidden = true;
        $('playerDuration').textContent = unknown;
        message(
          'previewError',
          'پلەیەر نەتوانی ڤیدیۆکە بکاتەوە؛ پێشبینین دووبارە پشکنین بکە.',
        );
        $('retryPreviewBtn').hidden = false;
      });
      async function initialize() {
        const source = read('source');
        const ticket = read('upload');
        const request = read('request');
        const savedOptions = read('options');
        if (savedOptions !== null) applyOptions(savedOptions);
        if (source && validSource(source)) {
          state.source = source;
          message('sourceIdentity', source.filename + ' · ' + source.source_id);
        } else if (source !== null) {
          state.storageReady = false;
          message('storageError', 'ناسنامەی سەرچاوەی پاشەکەوتکراو نادروستە.');
        }
        if (ticket && typeof ticket.upload_id === 'string' &&
            sourceIdPattern.test(ticket.upload_id) &&
            Number.isSafeInteger(ticket.size) && ticket.size > 0 &&
            Number.isFinite(ticket.expires_at) && ticket.expires_at > 0) {
          state.ticket = ticket;
          state.uploadUncertain = true;
          if (state.source && ticket.upload_id !== state.source.source_id) {
            state.storageReady = false;
            message('storageError', 'ناسنامەی سەرچاوە و بارکردن ناگونجێن.');
          }
        } else if (ticket !== null) {
          state.storageReady = false;
          message('storageError', 'ناسنامەی بارکردنی پاشەکەوتکراو نادروستە.');
        }
        if (request !== null) {
          if (
            request && typeof request === 'object' && !Array.isArray(request) &&
            request.schema === 1 &&
            Object.keys(request).sort().join(',') ===
              'client_token,options,schema,source_id' &&
            sourceIdPattern.test(request.source_id) &&
            typeof request.client_token === 'string' &&
            /^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$/.test(request.client_token) &&
            validOptions(request.options) &&
            state.source &&
            request.source_id === state.source.source_id
          ) {
            state.request = request;
            state.requestUncertain = true;
            applyOptions(request.options);
            message(
              'sourceError',
              'داواکاریی پێشوو ئەنجامی نەزانراوە؛ تەنها هەمان داواکاری پشکنین بکەرەوە.',
            );
          } else {
            state.storageReady = false;
            message(
              'storageError',
              'داواکاریی پاشەکەوتکراو ناسنامەی گونجاوی نییە؛ دووبارەی نوێ نانێردرێت.',
            );
          }
        }
        controls();
        await readiness();
        await refreshHistory(read('selected') || '');
        if (state.ticket) await recoverUpload();
      }
      initialize();
    </script>
  </body>
</html>
"""
