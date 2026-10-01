/* Claude <-> After Effects bridge: a tiny localhost server that runs ExtendScript inside AE
   and hands back real results, errors and rendered frames. Talks to tools/ae-bridge/mcp_ae.py. */
(function () {
  var http = require('http'), fs = require('fs'), os = require('os'), path = require('path'), crypto = require('crypto');
  var PORT = 37812;
  var HOME = os.homedir();
  var DIR = path.join(HOME, 'animations', '.ae-bridge');
  var FRAMES = path.join(DIR, 'frames');
  [DIR, FRAMES].forEach(function (d) { try { fs.mkdirSync(d, { recursive: true }); } catch (e) {} });

  var TOKEN_FILE = path.join(DIR, 'token'), token = '';
  try { token = fs.readFileSync(TOKEN_FILE, 'utf8').trim(); } catch (e) {}
  if (!token) { token = crypto.randomBytes(24).toString('hex'); fs.writeFileSync(TOKEN_FILE, token, { mode: 384 }); }

  var logEl = document.getElementById('log'), statusEl = document.getElementById('status'), count = 0;
  function log(msg, cls) {
    var d = document.createElement('div');
    d.className = 'row ' + (cls || '');
    d.innerHTML = '<span class="t">' + new Date().toTimeString().slice(0, 8) + '</span>  ' +
      String(msg).replace(/&/g, '&amp;').replace(/</g, '&lt;').slice(0, 400);
    logEl.appendChild(d);
    while (logEl.children.length > 200) logEl.removeChild(logEl.firstChild);
    logEl.scrollTop = logEl.scrollHeight;
  }

  // ---- one ExtendScript at a time, wrapped so errors come back instead of vanishing
  var queue = [], busy = false;
  function runJSX(code, timeout, cb) { queue.push([code, timeout || 120000, cb]); pump(); }
  function pump() {
    if (busy || !queue.length) return;
    busy = true;
    var job = queue.shift(), done = false;
    var timer = setTimeout(function () {
      if (done) return;
      done = true; busy = false;
      job[2]({ ok: false, error: 'timeout after ' + job[1] + 'ms (AE may be busy, or the script died silently)' });
      pump();
    }, job[1]);
    var wrapped = '(function(){ try { var __r = (function(){' + job[0] + '\n})();' +
      ' return "JSON:" + (typeof __r === "undefined" || __r === null ? "null" : __r.toString()); }' +
      ' catch (e) { return "ERR:" + e.toString() + (e.line ? " (line " + e.line + ")" : ""); } })()';
    window.__adobe_cep__.evalScript(wrapped, function (res) {
      if (done) return;
      done = true; clearTimeout(timer); busy = false;
      if (res === 'EvalScript error.') job[2]({ ok: false, error: 'EvalScript error (syntax error in the script)' });
      else if (res.indexOf('ERR:') === 0) job[2]({ ok: false, error: res.slice(4) });
      else if (res.indexOf('JSON:') === 0) job[2]({ ok: true, result: res.slice(5) });
      else job[2]({ ok: false, error: 'no result (the script aborted silently): ' + res });
      pump();
    });
  }

  // ---- ExtendScript snippets
  var Q = 'function q(s){return \'"\' + String(s).replace(/\\\\/g,"\\\\\\\\").replace(/"/g,\'\\\\"\').replace(/\\n/g,"\\\\n") + \'"\';}\n';
  var STATE = Q + [
    'var P = app.project, s = [];',
    's.push("\\"version\\":" + q(app.version));',
    's.push("\\"project\\":" + q(P && P.file ? P.file.fsName : "(unsaved)"));',
    's.push("\\"items\\":" + (P ? P.numItems : 0));',
    'var comps = [], i;',
    'for (i = 1; P && i <= P.numItems; i++) if (P.item(i) instanceof CompItem)',
    '  comps.push("{\\"name\\":" + q(P.item(i).name) + ",\\"w\\":" + P.item(i).width + ",\\"h\\":" + P.item(i).height +',
    '    ",\\"dur\\":" + P.item(i).duration.toFixed(3) + ",\\"fps\\":" + P.item(i).frameRate.toFixed(3) + ",\\"layers\\":" + P.item(i).numLayers + "}");',
    's.push("\\"comps\\":[" + comps.join(",") + "]");',
    'var c = (P && P.activeItem instanceof CompItem) ? P.activeItem : null;',
    'if (c) {',
    '  s.push("\\"active\\":" + q(c.name)); s.push("\\"time\\":" + c.time.toFixed(3));',
    '  var sel = [], sl = c.selectedLayers;',
    '  for (i = 0; i < sl.length; i++) sel.push("{\\"index\\":" + sl[i].index + ",\\"name\\":" + q(sl[i].name) +',
    '    ",\\"enabled\\":" + sl[i].enabled + ",\\"type\\":" + q(sl[i].matchName || "") + "}");',
    '  s.push("\\"selectedLayers\\":[" + sel.join(",") + "]");',
    '  var sp = [], pr = c.selectedProperties;',
    '  for (i = 0; i < pr.length; i++) sp.push(q(pr[i].name + " [" + pr[i].matchName + "]"));',
    '  s.push("\\"selectedProperties\\":[" + sp.join(",") + "]");',
    '} else { s.push("\\"active\\":null"); }',
    'var rq = [], SN = ["WILL_CONTINUE","NEEDS_OUTPUT","UNQUEUED","QUEUED","RENDERING","USER_STOPPED","ERR_STOPPED","DONE"];',
    'function rqs(v){ for (var k = 0; k < SN.length; k++) if (RQItemStatus[SN[k]] == v) return SN[k].toLowerCase().replace("_", " "); return String(v); }',
    'for (i = 1; P && i <= P.renderQueue.numItems; i++) rq.push("{\\"index\\":" + i + ",\\"comp\\":" +',
    '  q(P.renderQueue.item(i).comp.name) + ",\\"status\\":" + q(rqs(P.renderQueue.item(i).status)) + ",\\"file\\":" +',
    '  q(P.renderQueue.item(i).outputModule(1).file.fsName) + "}");',
    's.push("\\"renderQueue\\":[" + rq.join(",") + "]");',
    'return "{" + s.join(",") + "}";'
  ].join('\n');

  function frameJSX(compName, time, out) {
    return Q + [
      'var P = app.project, c = null, i;',
      compName ? 'for (i = 1; i <= P.numItems; i++) if (P.item(i) instanceof CompItem && P.item(i).name == ' +
        JSON.stringify(compName) + ') c = P.item(i);'
        : 'if (P.activeItem instanceof CompItem) c = P.activeItem;',
      'if (!c) throw new Error("no comp (open one or pass its name)");',
      'var t = ' + (time === null || time === undefined ? 'c.time' : Number(time)) + ';',
      'c.saveFrameToPng(t, new File(' + JSON.stringify(out) + '));',
      'return "{\\"comp\\":" + q(c.name) + ",\\"time\\":" + t + ",\\"w\\":" + c.width + ",\\"h\\":" + c.height + "}";'
    ].join('\n');
  }

  function waitFile(file, deadline, cb) {
    var last = -1;
    (function poll() {
      var st = null;
      try { st = fs.statSync(file); } catch (e) {}
      if (st && st.size > 0 && st.size === last) return cb(null);
      if (st) last = st.size;
      if (Date.now() > deadline) return cb(new Error('frame did not appear in time'));
      setTimeout(poll, 150);
    })();
  }

  // ---- HTTP
  function send(res, code, obj) {
    var body = JSON.stringify(obj);
    res.writeHead(code, { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) });
    res.end(body);
  }

  var server = http.createServer(function (req, res) {
    if (req.headers['x-bridge-token'] !== token) { log('rejected request without token', 'err'); return send(res, 403, { error: 'bad token' }); }
    var chunks = '';
    req.on('data', function (d) { chunks += d; });
    req.on('end', function () {
      var body = {};
      try { body = chunks ? JSON.parse(chunks) : {}; } catch (e) { return send(res, 400, { error: 'bad json' }); }
      var url = req.url.split('?')[0];
      count++;
      if (url === '/ping') return send(res, 200, { ok: true, port: PORT, calls: count });
      if (url === '/reload') {                      // pick up edits to this file without restarting AE
        send(res, 200, { ok: true, reloading: true });
        return setTimeout(function () { try { server.close(); } catch (e) {} location.reload(); }, 100);
      }
      if (url === '/state') {
        log('state');
        return runJSX(STATE, 30000, function (r) { send(res, 200, r); });
      }
      if (url === '/eval') {
        if (!body.code) return send(res, 400, { error: 'no code' });
        log('eval ' + body.code.replace(/\s+/g, ' ').slice(0, 120));
        return runJSX(body.code, body.timeout || 120000, function (r) {
          log(r.ok ? '  -> ' + String(r.result).slice(0, 120) : '  !! ' + r.error, r.ok ? 'ok' : 'err');
          send(res, 200, r);
        });
      }
      if (url === '/frame') {
        var out = path.join(FRAMES, 'frame_' + Date.now() + '.png');
        log('frame ' + (body.comp || '(active)') + ' @ ' + (body.time === undefined ? '(current)' : body.time));
        return runJSX(frameJSX(body.comp, body.time, out), 60000, function (r) {
          if (!r.ok) { log('  !! ' + r.error, 'err'); return send(res, 200, r); }
          waitFile(out, Date.now() + (body.timeout || 120000), function (err) {
            if (err) { log('  !! ' + err.message, 'err'); return send(res, 200, { ok: false, error: err.message }); }
            log('  -> ' + path.basename(out), 'ok');
            send(res, 200, { ok: true, result: r.result, file: out });
          });
        });
      }
      send(res, 404, { error: 'unknown endpoint' });
    });
  });

  server.on('error', function (e) {
    statusEl.className = 'off';
    statusEl.textContent = 'server error: ' + e.code + (e.code === 'EADDRINUSE' ? ' (another panel already running?)' : '');
    log(e.message, 'err');
  });
  server.listen(PORT, '127.0.0.1', function () {
    statusEl.className = 'on';
    statusEl.textContent = 'listening on 127.0.0.1:' + PORT;
    log('token: ' + TOKEN_FILE);
    log('ready — Claude can run scripts, read state and grab frames');
  });
  window.addEventListener('beforeunload', function () { try { server.close(); } catch (e) {} });
})();
