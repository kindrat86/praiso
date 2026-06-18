(function() {
  var BASE = '{{ base_url }}';
  var PID = '{{ project_uid }}';

  function loadWidget() {
    fetch(BASE + '/api/widget/' + PID)
      .then(function(r) { return r.json(); })
      .then(function(data) { render(data); })
      .catch(function(e) { console.error('Praiso widget error:', e); });
  }

  function stars(n) {
    var s = '';
    for (var i = 0; i < 5; i++) s += i < n ? '★' : '☆';
    return s;
  }

  function render(data) {
    var container = document.getElementById('praiso-widget');
    if (!container) return;

    var items = data.testimonials;
    if (!items || items.length === 0) {
      container.innerHTML = '';
      return;
    }

    var theme = data.project.theme || 'light';
    var style = data.project.style || 'carousel';
    var isDark = theme === 'dark';

    var bg = isDark ? '#1e293b' : '#ffffff';
    var text = isDark ? '#f1f5f9' : '#1e293b';
    var muted = isDark ? '#94a3b8' : '#64748b';
    var border = isDark ? '#334155' : '#e2e8f0';
    var starColor = '#f59e0b';

    var css = '\n' +
      '.praiso-wrap{font-family:Inter,system-ui,sans-serif;}\n' +
      '.praiso-card{background:' + bg + ';border:1px solid ' + border + ';border-radius:12px;padding:24px;}\n' +
      '.praiso-stars{color:' + starColor + ';font-size:16px;margin-bottom:8px;}\n' +
      '.praiso-text{color:' + text + ';font-size:15px;line-height:1.6;margin-bottom:12px;}\n' +
      '.praiso-author{font-size:13px;color:' + muted + ';}\n' +
      '.praiso-author strong{color:' + text + ';}\n' +
      '.praiso-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px;}\n' +
      '.praiso-carousel{display:flex;gap:16px;overflow-x:auto;scroll-snap-type:x mandatory;-webkit-overflow-scrolling:touch;padding-bottom:8px;}\n' +
      '.praiso-carousel .praiso-card{min-width:320px;max-width:400px;scroll-snap-align:start;flex-shrink:0;}\n' +
      '.praiso-wall{column-count:3;column-gap:16px;}\n' +
      '.praiso-wall .praiso-card{break-inside:avoid;margin-bottom:16px;}\n' +
      '@media(max-width:768px){.praiso-wall{column-count:1;}.praiso-carousel .praiso-card{min-width:280px;}}\n' +
      '.praiso-badge{font-size:11px;color:' + muted + ';text-align:right;margin-top:12px;}\n' +
      '.praiso-badge a{color:' + muted + ';text-decoration:none;}\n';

    var styleEl = document.createElement('style');
    styleEl.textContent = css;
    container.appendChild(styleEl);

    var wrap = document.createElement('div');
    wrap.className = 'praiso-wrap';

    var grid = document.createElement('div');
    grid.className = style === 'carousel' ? 'praiso-carousel' : style === 'wall' ? 'praiso-wall' : 'praiso-grid';

    for (var i = 0; i < items.length; i++) {
      var t = items[i];
      var card = document.createElement('div');
      card.className = 'praiso-card';
      var authorLine = '<strong>' + escHtml(t.author_name) + '</strong>';
      if (t.author_title) authorLine += ' · ' + escHtml(t.author_title);
      if (t.author_company) authorLine += ' at ' + escHtml(t.author_company);
      card.innerHTML =
        '<div class="praiso-stars">' + stars(t.rating) + '</div>' +
        '<div class="praiso-text">"' + escHtml(t.content) + '"</div>' +
        '<div class="praiso-author">' + authorLine + '</div>';
      grid.appendChild(card);
    }

    wrap.appendChild(grid);

    var badge = document.createElement('div');
    badge.className = 'praiso-badge';
    badge.innerHTML = 'Powered by <a href="' + BASE + '" target="_blank">Praiso</a>';
    wrap.appendChild(badge);

    container.appendChild(wrap);
  }

  function escHtml(s) {
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadWidget);
  } else {
    loadWidget();
  }
})();
