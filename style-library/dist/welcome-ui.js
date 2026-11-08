/* Task 19: first-run welcome on the videos home page -- "your first video in 3 steps", shown once.
   studio.js's home() calls WelcomeCard.render() every time it redraws #projects-page; the card goes right
   under the home heading until it is dismissed. Dismissal is saved in settings.json ("welcome_seen": true)
   through /ui-welcome, with the same guards as /ui-motion. The entrance fade plays once per page load and
   the CSS turns it off for the Motion setting "off" (and for reduced motion unless Motion is "always"). */
window.WelcomeCard = (() => {
  const STEPS = ['welcome.step1', 'welcome.step2', 'welcome.step3'];
  let seen = null; // null until /ui-welcome answers; an unreadable setting counts as seen (never nag)
  let entered = false;

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function notify(message) {
    const toast = document.querySelector('#toast');
    if (!toast) return;
    toast.textContent = message;
    toast.hidden = false;
    setTimeout(() => { toast.hidden = true; }, 3200);
  }

  function build() {
    const card = element('aside', 'first-run-welcome');
    card.setAttribute('aria-labelledby', 'first-run-welcome-title');
    if (!entered) { card.classList.add('is-entering'); entered = true; }
    card.append(element('p', 'eyebrow', I18N.t('welcome.eyebrow')));
    const title = element('h2', '', I18N.t('welcome.title'));
    title.id = 'first-run-welcome-title';
    card.append(title);
    const list = element('ol', 'first-run-steps');
    STEPS.forEach((key, index) => {
      const item = element('li');
      const number = element('span', 'first-run-num', String(index + 1));
      number.setAttribute('aria-hidden', 'true');
      item.append(number, element('strong', '', I18N.t(key + '.title')), element('span', 'first-run-body', I18N.t(key + '.body')));
      list.append(item);
    });
    card.append(list);
    const button = element('button', 'primary', I18N.t('welcome.dismiss'));
    button.type = 'button';
    button.addEventListener('click', dismiss);
    card.append(button);
    return card;
  }

  function render() {
    if (seen !== false) return;
    const page = document.querySelector('#projects-page');
    const heading = page && page.querySelector('.home-heading');
    if (!heading || page.querySelector('.first-run-welcome')) return;
    heading.after(build());
  }

  async function dismiss() {
    seen = true; // gone for this visit even if saving fails
    const page = document.querySelector('#projects-page');
    const card = page && page.querySelector('.first-run-welcome');
    if (card) card.remove();
    const start = page && page.querySelector('.home-heading [data-new-video]');
    if (start) start.focus();
    try {
      const response = await fetch('/ui-welcome', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-Studio-Action': 'ui-welcome'},
        body: JSON.stringify({welcome_seen: true}),
      });
      if (!response.ok) throw Error();
    } catch {
      notify(I18N.t('welcome.error'));
    }
  }

  const ready = fetch('/ui-welcome', {cache: 'no-store'})
    .then(response => (response.ok ? response.json() : null))
    .then(data => { seen = !(data && data.welcome_seen === false); })
    .catch(() => { seen = true; })
    .then(() => I18N.ready)
    .then(render);

  return {render, dismiss, ready};
})();
