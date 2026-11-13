// vimar_logger.js — registra in chiaro il traffico dell'app Vimar VIEW (OkHttp)
// senza proxy e senza certificati. Uso:
//   frida -U -f com.vimar.view -l vimar_logger.js -o vimar_log.txt
// ATTENZIONE: il log contiene token di accesso (scadono in pochi minuti) e dati dell'impianto.

Java.perform(function () {
    var MAX_BODY = 200000;

    // ── WebSocket ────────────────────────────────────────────────────────────
    try {
        var RWS = Java.use('okhttp3.internal.ws.RealWebSocket');
        RWS.send.overload('java.lang.String').implementation = function (text) {
            console.log('\n[WS >>] ' + text);
            return this.send(text);
        };
        RWS.onReadMessage.overload('java.lang.String').implementation = function (text) {
            console.log('\n[WS <<] ' + text);
            return this.onReadMessage(text);
        };
        console.log('[+] WebSocket OkHttp agganciato');
    } catch (e) {
        console.log('[-] RealWebSocket non trovato (classi offuscate?): ' + e);
    }

    // ── HTTP ─────────────────────────────────────────────────────────────────
    try {
        var Buffer = Java.use('okio.Buffer');
        var RealCall = Java.use('okhttp3.internal.connection.RealCall');
        var methodName = null;
        RealCall.class.getDeclaredMethods().forEach(function (m) {
            if (m.getName().indexOf('getResponseWithInterceptorChain') === 0) methodName = m.getName();
        });
        if (methodName === null) throw new Error('getResponseWithInterceptorChain non trovato');

        RealCall[methodName].implementation = function () {
            var req = this.getOriginalRequest ? this.getOriginalRequest() : this.originalRequest.value;
            var line = '\n[HTTP >>] ' + req.method() + ' ' + req.url().toString();
            try {
                var h = req.headers();
                for (var i = 0; i < h.size(); i++) {
                    var name = h.name(i), val = h.value(i);
                    if (name.toLowerCase() === 'authorization') val = val.substring(0, 12) + '…';
                    line += '\n  ' + name + ': ' + val;
                }
            } catch (e) {}
            try {
                var body = req.body();
                if (body !== null) {
                    var buf = Buffer.$new();
                    body.writeTo(buf);
                    line += '\n' + buf.readUtf8();
                }
            } catch (e) { line += '\n(corpo richiesta non leggibile: ' + e + ')'; }
            console.log(line);

            var resp = this[methodName]();
            try {
                console.log('[HTTP <<] ' + resp.code() + ' ' + req.url().toString() + '\n' +
                            resp.peekBody(MAX_BODY).string());
            } catch (e) { console.log('[HTTP <<] ' + resp.code() + ' (corpo non leggibile: ' + e + ')'); }
            return resp;
        };
        console.log('[+] HTTP OkHttp agganciato (' + methodName + ')');
    } catch (e) {
        console.log('[-] Hook HTTP non riuscito: ' + e);
    }

    // ── Diagnostica: se gli hook falliscono, elenca le classi OkHttp presenti ─
    setTimeout(function () {
        Java.perform(function () {
            var found = [];
            Java.enumerateLoadedClasses({
                onMatch: function (n) { if (n.indexOf('okhttp3') === 0 && n.indexOf('ws') !== -1) found.push(n); },
                onComplete: function () { console.log('[i] classi okhttp3 *ws*: ' + found.slice(0, 30).join(', ')); }
            });
        });
    }, 8000);
});
