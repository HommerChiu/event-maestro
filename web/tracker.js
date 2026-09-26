/*
 * maestro tracker: a tiny gtag.js look-alike.
 *
 * It keeps the same identifiers GA4 does (a client id that becomes
 * user_pseudo_id, ga_session_id / ga_session_number with a 30-minute
 * inactivity timeout), fires the "enhanced measurement" events GA4 collects
 * automatically, batches everything and POSTs it to /collect.
 *
 *   maestro.event('like_article', { article_id: 'a001' })
 *   maestro.pageView()                // call after each client-side route change
 *   maestro.setUserId('reader-42')    // after login / sign up
 *   maestro.setUserProperty('preferred_topic', 'lakehouse')
 *   maestro.onEvent(fn)               // debug console hook
 */
(function () {
  'use strict';

  var SESSION_TIMEOUT_MS = 30 * 60 * 1000;
  var ENGAGED_AFTER_MS = 10 * 1000;
  var FLUSH_DELAY_MS = 1000;
  var DOWNLOAD_RE = /\.(pdf|xlsx?|docx?|txt|rtf|csv|exe|key|pp[st]x?|7z|pkg|rar|gz|zip|avi|mov|mp4|mpe?g|wmv|midi?|mp3|wav|wma|md|sql|json)$/i;

  var store = {
    get: function (key) {
      try { return JSON.parse(localStorage.getItem('em_' + key)); } catch (e) { return null; }
    },
    set: function (key, value) {
      try { localStorage.setItem('em_' + key, JSON.stringify(value)); } catch (e) { /* private mode */ }
    }
  };

  function nowMicros() { return Math.round((performance.timeOrigin + performance.now()) * 1000); }
  function nowMs() { return Date.now(); }
  function randInt() { return Math.floor(Math.random() * 2147483647); }

  var queue = [];
  var listeners = [];
  var flushTimer = null;
  var pendingFirstEvents = [];

  // ---- identity ------------------------------------------------------------
  var client = store.get('client');
  var isNewUser = false;
  if (!client) {
    isNewUser = true;
    var firstMs = nowMs();
    client = { id: randInt() + '.' + Math.floor(firstMs / 1000), first_touch_micros: firstMs * 1000 };
    store.set('client', client);
  }
  var user = store.get('user') || { user_id: null, properties: {} };

  // ---- traffic source --------------------------------------------------------
  function readTrafficFromUrl() {
    var q = new URLSearchParams(location.search);
    if (q.get('utm_source') || q.get('gclid')) {
      return {
        source: q.get('utm_source') || (q.get('gclid') ? 'google' : null),
        medium: q.get('utm_medium') || (q.get('gclid') ? 'cpc' : null),
        campaign: q.get('utm_campaign'),
        term: q.get('utm_term'),
        content: q.get('utm_content'),
        gclid: q.get('gclid')
      };
    }
    if (document.referrer) {
      var ref = new URL(document.referrer);
      if (ref.host !== location.host) {
        var engine = /(^|\.)(google|bing|yahoo|duckduckgo)\./.exec(ref.hostname);
        return engine
          ? { source: engine[2], medium: 'organic', campaign: '(organic)' }
          : { source: ref.hostname, medium: 'referral', campaign: '(referral)' };
      }
    }
    return null;
  }

  var landingTraffic = readTrafficFromUrl();
  if (isNewUser) {
    store.set('first_traffic', landingTraffic || { source: '(direct)', medium: '(none)', campaign: '(direct)' });
  }

  // ---- session ---------------------------------------------------------------
  var session = store.get('session');
  var isNewSession = !session || nowMs() - session.last > SESSION_TIMEOUT_MS;
  if (isNewSession) {
    var previousNumber = session ? session.number : 0;
    session = {
      id: Math.floor(nowMs() / 1000),
      number: previousNumber + 1,
      last: nowMs(),
      engaged: false,
      page_views: 0,
      engagement_ms: 0
    };
    store.set('session', session);
  }

  function touchSession() {
    session.last = nowMs();
    if (!session.engaged && (session.engagement_ms >= ENGAGED_AFTER_MS || session.page_views >= 2)) {
      session.engaged = true;
    }
    store.set('session', session);
  }

  // ---- engagement timer (only counts while the tab is visible & focused) -----
  var engagedSince = document.visibilityState === 'visible' ? nowMs() : null;
  var pageEngagementMs = 0;

  function pauseEngagement() {
    if (engagedSince !== null) {
      var delta = nowMs() - engagedSince;
      pageEngagementMs += delta;
      session.engagement_ms += delta;
      engagedSince = null;
    }
  }
  function resumeEngagement() {
    if (engagedSince === null && document.visibilityState === 'visible') engagedSince = nowMs();
  }

  function sendUserEngagement() {
    pauseEngagement();
    if (pageEngagementMs > 0) {
      event('user_engagement', { engagement_time_msec: pageEngagementMs });
    }
    pageEngagementMs = 0;
    resumeEngagement();
  }

  // ---- core ------------------------------------------------------------------
  function event(name, params) {
    touchSession();
    var p = Object.assign({
      ga_session_id: session.id,
      ga_session_number: session.number,
      page_location: location.href,
      page_title: document.title,
      engaged_session_event: session.engaged ? 1 : 0
    }, params || {});
    if (session.engaged) p.session_engaged = '1';

    var evt = { name: name, timestamp_micros: nowMicros(), user_id: user.user_id, params: p, collected_traffic_source: null };
    if (pendingFirstEvents.indexOf(name) !== -1 && landingTraffic) {
      evt.collected_traffic_source = landingTraffic;
      pendingFirstEvents.splice(pendingFirstEvents.indexOf(name), 1);
    }
    queue.push(evt);
    listeners.forEach(function (fn) { try { fn(evt); } catch (e) { /* ignore */ } });
    scheduleFlush();
    return evt;
  }

  function payload(events) {
    return JSON.stringify({
      client_id: client.id,
      user_id: user.user_id,
      first_touch_micros: client.first_touch_micros,
      user_properties: user.properties,
      traffic_source: store.get('first_traffic'),
      language: navigator.language,
      hostname: location.hostname,
      events: events
    });
  }

  function scheduleFlush() {
    if (!flushTimer) flushTimer = setTimeout(flush, FLUSH_DELAY_MS);
  }

  function flush(useBeacon) {
    clearTimeout(flushTimer);
    flushTimer = null;
    if (!queue.length) return;
    var events = queue.splice(0, queue.length);
    var body = payload(events);
    if (useBeacon && navigator.sendBeacon) {
      navigator.sendBeacon('/collect', new Blob([body], { type: 'application/json' }));
      return;
    }
    fetch('/collect', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body, keepalive: true })
      .catch(function () { queue = events.concat(queue); });
  }

  // ---- page views & scroll -----------------------------------------------------
  var scrolledThisPage = false;
  var pagesThisLoad = 0;
  var lastLocation = document.referrer || '';

  function pageView(extra) {
    if (pagesThisLoad > 0) sendUserEngagement();
    pagesThisLoad += 1;
    session.page_views += 1;
    scrolledThisPage = false;
    var params = Object.assign({ page_referrer: lastLocation }, extra || {});
    lastLocation = location.href;
    return event('page_view', params);
  }

  window.addEventListener('scroll', function () {
    if (scrolledThisPage) return;
    var doc = document.documentElement;
    var max = doc.scrollHeight - window.innerHeight;
    if (max > 0 && window.scrollY / max >= 0.9) {
      scrolledThisPage = true;
      event('scroll', { percent_scrolled: 90 });
    }
  }, { passive: true });

  // ---- outbound clicks & file downloads ---------------------------------------
  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[href]');
    if (!a) return;
    var url = new URL(a.href, location.href);
    var text = (a.textContent || '').trim().slice(0, 100);
    if (DOWNLOAD_RE.test(url.pathname)) {
      var file = url.pathname.split('/').pop();
      event('file_download', {
        file_name: url.pathname,
        file_extension: file.split('.').pop(),
        link_url: url.href,
        link_text: text
      });
    } else if (url.host !== location.host && /^https?:$/.test(url.protocol)) {
      event('click', { link_url: url.href, link_domain: url.hostname, link_text: text, outbound: true });
    }
  }, true);

  // ---- lifecycle -----------------------------------------------------------------
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') {
      sendUserEngagement();
      pauseEngagement();
      flush(true);
    } else {
      resumeEngagement();
    }
  });
  window.addEventListener('pagehide', function () { flush(true); });
  window.addEventListener('blur', pauseEngagement);
  window.addEventListener('focus', resumeEngagement);

  // First events of a visit, in the order GA4 emits them.
  if (isNewSession) {
    pendingFirstEvents = (isNewUser ? ['first_visit'] : []).concat(['session_start', 'page_view']);
  }
  if (isNewUser) event('first_visit', {});
  if (isNewSession) event('session_start', {});

  window.maestro = {
    event: event,
    pageView: pageView,
    flush: flush,
    setUserId: function (id) {
      user.user_id = id || null;
      store.set('user', user);
    },
    setUserProperty: function (key, value) {
      user.properties[key] = value;
      store.set('user', user);
    },
    onEvent: function (fn) { listeners.push(fn); },
    /** Forget the current session so the next page load starts a new one. */
    resetSession: function () {
      flush(true);
      session.last = 0;
      store.set('session', session);
    },
    info: function () {
      return {
        user_pseudo_id: client.id,
        user_id: user.user_id,
        ga_session_id: session.id,
        ga_session_number: session.number,
        session_engaged: session.engaged,
        first_traffic: store.get('first_traffic')
      };
    }
  };
})();
