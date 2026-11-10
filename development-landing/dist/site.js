const services = [...document.querySelectorAll('#service-grid [data-service]')].map(link => ({
  id: link.dataset.service,
  name: link.closest('.card').querySelector('h3').textContent,
  price: Number(link.dataset.price)
}));
services.push({ id: 'custom', name: 'Несколько услуг / другая задача' });

const formatPrice = new Intl.NumberFormat('ru-KG');
const priceLabel = service => service.price ? `от ${formatPrice.format(service.price)} сом` : 'По запросу';
const select = document.querySelector('#service');
const description = document.querySelector('#description');
const estimate = document.querySelector('#estimate');
const briefStatus = document.querySelector('#brief-status');

for (const service of services) {
  select.add(new Option(service.name, service.id));
}

function updateEstimate() {
  const service = services.find(item => item.id === select.value);
  estimate.textContent = service ? `Ориентир: ${priceLabel(service)}` : 'Выберите услугу, чтобы увидеть стартовую цену';
  briefStatus.textContent = '';
}

select.addEventListener('change', updateEstimate);
description.addEventListener('input', () => {
  description.setCustomValidity('');
  briefStatus.textContent = '';
});
document.querySelector('#service-grid').addEventListener('click', event => {
  const link = event.target.closest('[data-service]');
  if (!link) return;
  select.value = link.dataset.service;
  updateEstimate();
});

const form = document.querySelector('#brief-form');
form.addEventListener('submit', async event => {
  event.preventDefault();
  const task = description.value.trim();
  if (task.length < 5) {
    description.setCustomValidity('Опишите задачу хотя бы в нескольких словах.');
    description.reportValidity();
    return;
  }
  const data = new FormData(form);
  const service = services.find(item => item.id === select.value);
  const button = form.querySelector('[type=submit]');
  button.disabled = true;
  briefStatus.textContent = 'Отправляю…';
  try {
    const response = await fetch('/api/leads', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name: data.get('name'), contact: data.get('contact'), body: service.name + ': ' + task})
    });
    const result = await response.json();
    if (!response.ok) {
      briefStatus.textContent = result.error || 'Не удалось отправить заявку.';
      return;
    }
    form.reset();
    updateEstimate();
    briefStatus.textContent = 'Заявка №' + result.id + ' принята. Спасибо!';
  } catch {
    briefStatus.textContent = 'Связь прервалась. Попробуйте ещё раз.';
  } finally {
    button.disabled = false;
  }
});

fetch('/api/contacts').then(response => response.json()).then(contacts => {
  const links = document.querySelector('#contact-actions');
  for (const link of links.querySelectorAll('[data-contact]')) {
    const url = contacts[link.dataset.contact];
    if (typeof url === 'string' && /^https:\/\/(wa\.me|t\.me)\//.test(url)) {
      link.href = url;
      link.hidden = false;
      links.hidden = false;
    }
  }
}).catch(() => {});

const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
const mesh = document.querySelector('#mesh');
const orb = document.querySelector('#orb');
const svgNamespace = 'http://www.w3.org/2000/svg';
const rings = [];
for (let ring = 1; ring < 19; ring++) {
  const path = document.createElementNS(svgNamespace, 'path');
  path.setAttribute('stroke', '#d9dfe8');
  path.setAttribute('stroke-opacity', '0.65');
  mesh.append(path);
  rings.push(path);
}

function renderMesh(time) {
  const rotation = time * 0.00065;
  for (const [index, path] of rings.entries()) {
    const latitude = Math.PI * ((index + 1) / 19 - 0.5);
    const radius = Math.cos(latitude);
    const y = Math.sin(latitude);
    const points = [];
    for (let sample = 0; sample <= 96; sample++) {
      const angle = sample / 96 * Math.PI * 2;
      const wave = 1 + 0.12 * Math.cos(5 * angle + 3 * y - rotation) + 0.05 * Math.sin(9 * angle + rotation);
      const x = radius * Math.cos(angle) * wave;
      const z = radius * Math.sin(angle) * wave;
      const vertical = (y * 0.93 - z * 0.37) * 178;
      const horizontal = x * 178;
      points.push(`${(280 + horizontal * 0.91 - vertical * 0.42).toFixed(1)},${(260 + horizontal * 0.42 + vertical * 0.91).toFixed(1)}`);
    }
    path.setAttribute('d', `M${points.join('L')}Z`);
  }
}

let visible = false;
let frame = 0;
let lastPaint = -Infinity;
function animate(time) {
  if (time - lastPaint >= 32) {
    renderMesh(time);
    lastPaint = time;
  }
  frame = requestAnimationFrame(animate);
}
function syncAnimation() {
  cancelAnimationFrame(frame);
  if (visible && !reducedMotion.matches) frame = requestAnimationFrame(animate);
}
renderMesh(0);
const orbObserver = new IntersectionObserver(([entry]) => {
  visible = entry.isIntersecting;
  syncAnimation();
});
orbObserver.observe(orb);
reducedMotion.addEventListener('change', syncAnimation);
