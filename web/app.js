/*
 * Pixel Notes: a small single-page knowledge-sharing site.
 * Every meaningful interaction calls maestro.event(...) so it lands in the
 * GA4-style event log. See docs/events.md for the full event dictionary.
 */
(function () {
  'use strict';

  var app = document.getElementById('app');
  var state = { authors: {}, topics: {}, articles: [], byId: {} };

  // ---- tiny helpers ------------------------------------------------------------
  function h(html) { var t = document.createElement('template'); t.innerHTML = html.trim(); return t.content; }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function local(key, fallback) {
    try { var v = JSON.parse(localStorage.getItem('pn_' + key)); return v == null ? fallback : v; } catch (e) { return fallback; }
  }
  function saveLocal(key, value) { try { localStorage.setItem('pn_' + key, JSON.stringify(value)); } catch (e) { /* ignore */ } }
  function toast(msg) {
    var el = document.getElementById('toast');
    el.textContent = msg;
    el.classList.add('show');
    clearTimeout(toast.t);
    toast.t = setTimeout(function () { el.classList.remove('show'); }, 1800);
  }
  function articleParams(a) {
    return {
      article_id: a.id,
      article_title: a.title,
      author: a.author_name,
      topic: a.topic,
      content_group: a.topic_name,
      word_count: a.word_count,
      reading_time_min: a.reading_time_min
    };
  }

  // ---- pixel art ---------------------------------------------------------------
  // Each sprite is an 8x8 grid; characters map to palette colours.
  var PALETTE = { k: '#1a1c2c', p: '#5d275d', r: '#b13e53', o: '#ef7d57', y: '#ffcd75', g: '#a7f070', G: '#38b764', t: '#257179', n: '#29366f', b: '#3b5dc9', c: '#41a6f6', C: '#73eff7', w: '#f4f4f4', s: '#94b0c2', S: '#566c86' };
  var SPRITES = {
    wizard: ['...pp...', '..pppp..', '.pppppp.', '..yyyy..', '..ykyk..', '..yyyy..', '.bbbbbb.', '.b.bb.b.'],
    knight: ['..ssss..', '.ssssss.', '.sSkkSs.', '.ssssss.', '..ssss..', '.rrrrrr.', '.rrwwrr.', '.s....s.'],
    robot: ['...cc...', '.CCCCCC.', '.CkCCkC.', '.CCCCCC.', '.C.rr.C.', '.SSSSSS.', '.S.SS.S.', '.S....S.'],
    slime: ['........', '...gg...', '..gggg..', '.gggggg.', '.gkggkg.', 'gggggggg', 'gGggggGg', '.GGGGGG.'],
    heart: ['........', '.rr.rr..', 'rrrrrrr.', 'rrrrrrr.', '.rrrrr..', '..rrr...', '...r....', '........'],
    heartOff: ['........', '.ss.ss..', 's..s..s.', 's.....s.', '.s...s..', '..s.s...', '...s....', '........'],
    flag: ['.yyyyy..', '.yyyyy..', '.yyyyy..', '.yyyyy..', '.yyyyy..', '.yy.yy..', '.y...y..', '........'],
    flagOff: ['.sssss..', '.s...s..', '.s...s..', '.s...s..', '.s...s..', '.ss.ss..', '.s...s..', '........'],
    book: ['........', '.nnnnnn.', '.nwwwwn.', '.nwsswn.', '.nwwwwn.', '.nwsswn.', '.nnnnnn.', '........'],
    star: ['...y....', '...y....', '.yyyyy..', '..yyy...', '..y.y...', '.y...y..', '........', '........']
  };
  function sprite(name, size) {
    var rows = SPRITES[name] || SPRITES.book;
    var rects = '';
    rows.forEach(function (row, y) {
      row.split('').forEach(function (ch, x) {
        if (PALETTE[ch]) rects += '<rect x="' + x + '" y="' + y + '" width="1" height="1" fill="' + PALETTE[ch] + '"/>';
      });
    });
    return '<svg class="sprite" width="' + (size || 32) + '" height="' + (size || 32) + '" viewBox="0 0 8 8" shape-rendering="crispEdges" aria-hidden="true">' + rects + '</svg>';
  }

  // ---- router ------------------------------------------------------------------
  var routes = [
    [/^\/$/, renderHome],
    [/^\/topics\/([\w-]+)$/, renderTopic],
    [/^\/articles\/([\w-]+)$/, renderArticle],
    [/^\/search$/, renderSearch],
    [/^\/bookmarks$/, renderBookmarks],
    [/^\/login$/, renderLogin]
  ];

  function navigate(url, replace) {
    if (replace) history.replaceState({}, '', url); else history.pushState({}, '', url);
    render();
  }

  var cleanupFns = [];
  function onCleanup(fn) { cleanupFns.push(fn); }

  function render() {
    cleanupFns.splice(0).forEach(function (fn) { fn(); });
    var path = location.pathname;
    for (var i = 0; i < routes.length; i++) {
      var m = routes[i][0].exec(path);
      if (m) { routes[i][1].apply(null, m.slice(1)); window.scrollTo(0, 0); updateNav(); return; }
    }
    renderNotFound();
  }

  document.addEventListener('click', function (e) {
    var a = e.target.closest('a[data-link]');
    if (!a || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    var article = a.getAttribute('data-article');
    if (article && state.byId[article]) {
      maestro.event('select_content', Object.assign({
        content_type: 'article',
        content_id: article,
        item_list_name: a.getAttribute('data-list') || null
      }, articleParams(state.byId[article])));
    }
    navigate(a.getAttribute('href'));
  });
  window.addEventListener('popstate', render);

  function setPage(title, html, extraPageParams) {
    document.title = title + ' · Pixel Notes';
    app.innerHTML = '';
    app.appendChild(h(html));
    maestro.pageView(extraPageParams);
  }

  function updateNav() {
    var info = maestro.info();
    var nav = document.getElementById('nav-account');
    nav.textContent = info.user_id ? '👾 ' + local('display_name', info.user_id) : '登入';
  }

  // ---- views -------------------------------------------------------------------
  function card(a, listName, index) {
    var author = state.authors[a.author];
    return '<article class="card">' +
      '<a class="card-link" href="/articles/' + a.id + '" data-link data-article="' + a.id + '" data-list="' + esc(listName) + '" data-index="' + index + '">' +
      '<div class="card-top"><span class="tag tag-' + a.topic + '">' + esc(a.topic_name) + '</span><span class="muted small">' + a.reading_time_min + ' 分鐘</span></div>' +
      '<h3>' + esc(a.title) + '</h3>' +
      '<p>' + esc(a.summary) + '</p>' +
      '<div class="byline">' + sprite(author.avatar, 24) + '<span>' + esc(author.name) + '</span><span class="muted small">' + a.published_at + '</span></div>' +
      '</a></article>';
  }

  function topicChips(active) {
    return '<div class="chips">' +
      '<a class="chip' + (active ? '' : ' active') + '" href="/" data-link>全部</a>' +
      Object.keys(state.topics).map(function (k) {
        return '<a class="chip' + (active === k ? ' active' : '') + '" href="/topics/' + k + '" data-link>' + esc(state.topics[k]) + '</a>';
      }).join('') + '</div>';
  }

  function renderHome() {
    var list = state.articles.slice().sort(function (a, b) { return b.published_at.localeCompare(a.published_at); });
    setPage('首頁',
      '<section class="hero panel">' +
        '<div class="hero-art">' + sprite('wizard', 64) + sprite('knight', 64) + sprite('robot', 64) + sprite('slime', 64) + '</div>' +
        '<div><h1>LEVEL UP YOUR DATA SKILLS</h1><p>像素筆記：一群資料人把踩過的坑、學到的架構寫成文章。</p></div>' +
      '</section>' +
      topicChips(null) +
      '<h2 class="section-title">▶ 最新文章</h2>' +
      '<div class="grid">' + list.map(function (a, i) { return card(a, 'latest', i); }).join('') + '</div>',
      { content_group: 'home' });
  }

  function renderTopic(topic) {
    var list = state.articles.filter(function (a) { return a.topic === topic; });
    var name = state.topics[topic] || topic;
    setPage(name,
      topicChips(topic) +
      '<h2 class="section-title">▶ ' + esc(name) + '（' + list.length + '）</h2>' +
      '<div class="grid">' + list.map(function (a, i) { return card(a, 'topic_' + topic, i); }).join('') + '</div>',
      { content_group: 'topic', topic: topic });
  }

  function renderSearch() {
    var q = (new URLSearchParams(location.search).get('q') || '').trim();
    document.getElementById('search-input').value = q;
    var needle = q.toLowerCase();
    var list = !needle ? [] : state.articles.filter(function (a) {
      return (a.title + ' ' + a.summary + ' ' + a.tags.join(' ') + ' ' + a.topic_name).toLowerCase().indexOf(needle) !== -1;
    });
    setPage('搜尋：' + q,
      '<h2 class="section-title">▶ 搜尋「' + esc(q) + '」共 ' + list.length + ' 筆</h2>' +
      (list.length ? '<div class="grid">' + list.map(function (a, i) { return card(a, 'search_results', i); }).join('') + '</div>'
                   : '<div class="panel empty">' + sprite('slime', 48) + '<p>GAME OVER… 找不到相關文章，換個關鍵字試試？</p></div>'),
      { content_group: 'search' });
    // GA4 fires view_search_results when the URL carries a search query parameter.
    if (q) maestro.event('view_search_results', { search_term: q, search_results: list.length });
  }

  function renderBookmarks() {
    var ids = local('bookmarks', []);
    var list = ids.map(function (id) { return state.byId[id]; }).filter(Boolean);
    setPage('我的收藏',
      '<h2 class="section-title">▶ 我的收藏（' + list.length + '）</h2>' +
      (list.length ? '<div class="grid">' + list.map(function (a, i) { return card(a, 'bookmarks', i); }).join('') + '</div>'
                   : '<div class="panel empty">' + sprite('flagOff', 48) + '<p>還沒有收藏任何文章。</p></div>'),
      { content_group: 'bookmarks' });
  }

  function renderArticle(id) {
    var a = state.byId[id];
    if (!a) return renderNotFound();
    var author = state.authors[a.author];
    var liked = local('likes', []).indexOf(id) !== -1;
    var bookmarked = local('bookmarks', []).indexOf(id) !== -1;
    var comments = local('comments_' + id, []);
    var related = state.articles.filter(function (x) { return x.topic === a.topic && x.id !== a.id; }).slice(0, 3);

    setPage(a.title,
      '<article class="post panel">' +
        '<div class="card-top"><a class="tag tag-' + a.topic + '" href="/topics/' + a.topic + '" data-link>' + esc(a.topic_name) + '</a>' +
        '<span class="muted small">' + a.published_at + ' · ' + a.reading_time_min + ' 分鐘閱讀</span></div>' +
        '<h1>' + esc(a.title) + '</h1>' +
        '<div class="byline">' + sprite(author.avatar, 32) + '<span><strong>' + esc(author.name) + '</strong> <span class="muted">' + esc(author.title) + '</span></span></div>' +
        '<div class="progress" aria-hidden="true"><div class="progress-bar" id="read-bar"></div></div>' +
        '<p class="lead">' + esc(a.summary) + '</p>' +
        a.body.map(function (p) { return '<p>' + esc(p) + '</p>'; }).join('') +
        (a.code ? '<div class="code"><button class="btn btn-small copy" type="button" id="copy-code">COPY</button><pre><code>' + esc(a.code) + '</code></pre></div>' : '') +
        (a.links.length ? '<h3>延伸閱讀</h3><ul class="links">' + a.links.map(function (l) {
          return '<li><a href="' + esc(l.url) + '" target="_blank" rel="noopener">' + esc(l.label) + ' ↗</a></li>';
        }).join('') + '</ul>' : '') +
        (a.download ? '<p><a class="btn btn-accent" href="/files/' + esc(a.download) + '" download>⬇ 下載 ' + esc(a.download) + '</a></p>' : '') +
        '<div class="tags">' + a.tags.map(function (t) { return '<a class="chip" href="/search?q=' + encodeURIComponent(t) + '" data-link>#' + esc(t) + '</a>'; }).join('') + '</div>' +
        '<div class="actions">' +
          '<button class="btn" type="button" id="like-btn" aria-pressed="' + liked + '">' + sprite(liked ? 'heart' : 'heartOff', 20) + ' <span>' + (liked ? '已按讚' : '按讚') + '</span></button>' +
          '<button class="btn" type="button" id="bookmark-btn" aria-pressed="' + bookmarked + '">' + sprite(bookmarked ? 'flag' : 'flagOff', 20) + ' <span>' + (bookmarked ? '已收藏' : '收藏') + '</span></button>' +
          '<button class="btn" type="button" data-share="copy_link">🔗 複製連結</button>' +
          '<button class="btn" type="button" data-share="x">𝕏 分享</button>' +
          '<button class="btn" type="button" data-share="facebook">f 分享</button>' +
        '</div>' +
      '</article>' +
      '<section class="panel comments">' +
        '<h3>💬 留言（<span id="comment-count">' + comments.length + '</span>）</h3>' +
        '<ol id="comment-list">' + comments.map(commentItem).join('') + '</ol>' +
        '<form id="comment-form" class="row"><input name="body" required maxlength="280" placeholder="留下你的想法…"><button class="btn btn-accent" type="submit">送出</button></form>' +
      '</section>' +
      (related.length ? '<h2 class="section-title">▶ 同主題文章</h2><div class="grid">' + related.map(function (x, i) { return card(x, 'related_articles', i); }).join('') + '</div>' : ''),
      articleParams(a));

    var params = articleParams(a);

    // read_progress: 25 / 50 / 75 / 100 % of the article body scrolled past.
    var post = app.querySelector('.post');
    var bar = document.getElementById('read-bar');
    var fired = {};
    var readStart = Date.now();
    function onScroll() {
      var rect = post.getBoundingClientRect();
      var total = rect.height - window.innerHeight * 0.4;
      var pct = total > 0 ? Math.min(100, Math.max(0, (-rect.top + window.innerHeight * 0.6) / total * 100)) : 100;
      bar.style.width = pct + '%';
      [25, 50, 75, 100].forEach(function (mark) {
        if (pct >= mark && !fired[mark]) {
          fired[mark] = true;
          maestro.event('read_progress', Object.assign({ percent_read: mark, seconds_on_page: Math.round((Date.now() - readStart) / 1000) }, params));
        }
      });
    }
    window.addEventListener('scroll', onScroll, { passive: true });
    onCleanup(function () { window.removeEventListener('scroll', onScroll); });
    setTimeout(onScroll, 300);

    document.getElementById('like-btn').addEventListener('click', function () {
      var likes = local('likes', []);
      var on = likes.indexOf(id) === -1;
      saveLocal('likes', on ? likes.concat(id) : likes.filter(function (x) { return x !== id; }));
      maestro.event(on ? 'like_article' : 'unlike_article', params);
      this.innerHTML = sprite(on ? 'heart' : 'heartOff', 20) + ' <span>' + (on ? '已按讚' : '按讚') + '</span>';
      this.setAttribute('aria-pressed', on);
      if (on) toast('♥ +1 EXP');
    });

    document.getElementById('bookmark-btn').addEventListener('click', function () {
      var marks = local('bookmarks', []);
      var on = marks.indexOf(id) === -1;
      saveLocal('bookmarks', on ? marks.concat(id) : marks.filter(function (x) { return x !== id; }));
      maestro.event(on ? 'bookmark_article' : 'remove_bookmark', params);
      this.innerHTML = sprite(on ? 'flag' : 'flagOff', 20) + ' <span>' + (on ? '已收藏' : '收藏') + '</span>';
      this.setAttribute('aria-pressed', on);
      toast(on ? '已加入收藏' : '已移除收藏');
    });

    app.querySelectorAll('[data-share]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var method = btn.getAttribute('data-share');
        maestro.event('share', Object.assign({ method: method, content_type: 'article', item_id: id }, params));
        if (method === 'copy_link' && navigator.clipboard) navigator.clipboard.writeText(location.href).catch(function () {});
        toast(method === 'copy_link' ? '連結已複製' : '已分享到 ' + method + '（模擬）');
      });
    });

    var copy = document.getElementById('copy-code');
    if (copy) copy.addEventListener('click', function () {
      if (navigator.clipboard) navigator.clipboard.writeText(a.code).catch(function () {});
      maestro.event('copy_code', Object.assign({ code_lines: a.code.split('\n').length }, params));
      toast('程式碼已複製');
    });

    document.getElementById('comment-form').addEventListener('submit', function (e) {
      e.preventDefault();
      var input = this.elements.body;
      var body = input.value.trim();
      if (!body) return;
      var list = local('comments_' + id, []);
      var item = { name: local('display_name', '匿名讀者'), body: body, at: new Date().toISOString().slice(0, 10) };
      list.push(item);
      saveLocal('comments_' + id, list);
      document.getElementById('comment-list').appendChild(h(commentItem(item)));
      document.getElementById('comment-count').textContent = list.length;
      maestro.event('submit_comment', Object.assign({ comment_length: body.length, logged_in: maestro.info().user_id ? 1 : 0 }, params));
      input.value = '';
      toast('留言成功！');
    });
  }

  function commentItem(c) {
    return '<li>' + sprite('star', 16) + ' <strong>' + esc(c.name) + '</strong> <span class="muted small">' + esc(c.at) + '</span><p>' + esc(c.body) + '</p></li>';
  }

  function renderLogin() {
    var info = maestro.info();
    if (info.user_id) {
      setPage('帳號',
        '<section class="panel narrow"><h2>👾 ' + esc(local('display_name', info.user_id)) + '</h2>' +
        '<p class="muted">user_id：<code>' + esc(info.user_id) + '</code></p>' +
        '<button class="btn" id="logout" type="button">登出</button></section>',
        { content_group: 'account' });
      document.getElementById('logout').addEventListener('click', function () {
        maestro.setUserId(null);
        saveLocal('display_name', null);
        toast('已登出');
        navigate('/');
      });
      return;
    }
    setPage('登入 / 註冊',
      '<section class="panel narrow">' +
        '<h2>PLAYER SELECT</h2>' +
        '<p class="muted">登入後的事件會帶上 <code>user_id</code>，可以練習跨裝置的使用者合併。</p>' +
        '<form id="auth-form" class="stack">' +
          '<label>暱稱<input name="name" required maxlength="20" placeholder="例如：Ben"></label>' +
          '<label>Email<input name="email" type="email" required placeholder="you@example.com"></label>' +
          '<div class="row"><button class="btn btn-accent" type="submit" data-mode="sign_up">註冊新帳號</button>' +
          '<button class="btn" type="submit" data-mode="login">登入</button></div>' +
          '<div class="row"><button class="btn" type="button" id="github-login">🐙 用 GitHub 登入</button></div>' +
        '</form>' +
      '</section>',
      { content_group: 'account' });

    function finish(mode, method, name, email) {
      var userId = 'reader-' + Math.abs(hash(email || name)).toString(36);
      maestro.setUserId(userId);
      saveLocal('display_name', name);
      maestro.event(mode, { method: method });
      toast(mode === 'sign_up' ? '註冊成功！歡迎新玩家' : '歡迎回來！');
      navigate('/');
    }
    var form = document.getElementById('auth-form');
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var mode = (e.submitter && e.submitter.getAttribute('data-mode')) || 'login';
      finish(mode, 'email', form.elements.name.value.trim(), form.elements.email.value.trim().toLowerCase());
    });
    document.getElementById('github-login').addEventListener('click', function () {
      var name = form.elements.name.value.trim() || 'octocat';
      finish('login', 'github', name, name + '@github');
    });
  }

  function renderNotFound() {
    setPage('404',
      '<div class="panel empty">' + sprite('robot', 64) + '<h2>404 · STAGE NOT FOUND</h2><p><a href="/" data-link>回到首頁</a></p></div>',
      { content_group: 'not_found' });
  }

  function hash(s) {
    var x = 0;
    for (var i = 0; i < s.length; i++) x = (x * 31 + s.charCodeAt(i)) | 0;
    return x;
  }

  // ---- global forms --------------------------------------------------------------
  document.getElementById('search-form').addEventListener('submit', function (e) {
    e.preventDefault();
    var q = this.elements.q.value.trim();
    if (!q) return;
    maestro.event('search', { search_term: q });
    navigate('/search?q=' + encodeURIComponent(q));
  });

  document.getElementById('newsletter-form').addEventListener('submit', function (e) {
    e.preventDefault();
    var already = local('subscribed', false);
    maestro.event('subscribe_newsletter', { newsletter: 'weekly_digest', already_subscribed: already ? 1 : 0, form_location: 'footer' });
    maestro.setUserProperty('newsletter_subscriber', 'yes');
    saveLocal('subscribed', true);
    this.reset();
    toast('📮 訂閱成功！');
  });

  // ---- debug console ---------------------------------------------------------------
  var debug = document.getElementById('debug');
  var toggle = document.getElementById('debug-toggle');
  var log = document.getElementById('debug-log');
  function setDebug(open) {
    debug.hidden = !open;
    toggle.setAttribute('aria-expanded', open);
    saveLocal('debug_open', open);
    if (open) renderDebugMeta();
  }
  toggle.addEventListener('click', function () { setDebug(debug.hidden); });
  document.getElementById('debug-close').addEventListener('click', function () { setDebug(false); });

  function renderDebugMeta() {
    var i = maestro.info();
    document.getElementById('debug-meta').innerHTML =
      '<div><span class="muted">user_pseudo_id</span> ' + esc(i.user_pseudo_id) + '</div>' +
      '<div><span class="muted">user_id</span> ' + esc(i.user_id || '—') + '</div>' +
      '<div><span class="muted">ga_session_id</span> ' + esc(i.ga_session_id) + ' <span class="muted">#' + i.ga_session_number + '</span>' + (i.session_engaged ? ' <span class="tag tag-quality">engaged</span>' : '') + '</div>' +
      '<div><span class="muted">first source</span> ' + esc(i.first_traffic ? i.first_traffic.source + ' / ' + i.first_traffic.medium : '—') + '</div>';
  }

  maestro.onEvent(function (evt) {
    var p = Object.assign({}, evt.params);
    ['ga_session_id', 'ga_session_number', 'page_location', 'page_title', 'engaged_session_event', 'session_engaged'].forEach(function (k) { delete p[k]; });
    var li = document.createElement('li');
    li.innerHTML = '<span class="ev ev-' + esc(evt.name) + '">' + esc(evt.name) + '</span> <span class="muted small">' +
      new Date(evt.timestamp_micros / 1000).toLocaleTimeString() + '</span><code>' + esc(JSON.stringify(p)) + '</code>';
    log.insertBefore(li, log.firstChild);
    while (log.children.length > 60) log.removeChild(log.lastChild);
    if (!debug.hidden) renderDebugMeta();
  });

  debug.querySelectorAll('[data-utm]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var parts = btn.getAttribute('data-utm').split('/');
      var q = new URLSearchParams({ utm_source: parts[0], utm_medium: parts[1] });
      if (parts[2]) q.set('utm_campaign', parts[2]);
      maestro.resetSession();
      location.href = location.pathname + '?' + q.toString();
    });
  });

  // ---- boot ----------------------------------------------------------------------
  fetch('/api/articles').then(function (r) { return r.json(); }).then(function (data) {
    state.authors = data.authors;
    state.topics = data.topics;
    state.articles = data.articles;
    data.articles.forEach(function (a) { state.byId[a.id] = a; });
    render();
    if (local('debug_open', false)) setDebug(true);
  });
})();
