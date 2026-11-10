// Set a public Telegram, WhatsApp or email link to enable direct contact.
const contactUrl = '';

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
const result = document.querySelector('#brief-result');
const briefText = document.querySelector('#brief-text');
const briefStatus = document.querySelector('#brief-status');

for (const service of services) {
  select.add(new Option(service.name, service.id));
}

function updateEstimate() {
  const service = services.find(item => item.id === select.value);
  estimate.textContent = service ? `Ориентир: ${priceLabel(service)}` : 'Выберите услугу, чтобы увидеть стартовую цену';
  result.hidden = true;
}

select.addEventListener('change', updateEstimate);
description.addEventListener('input', () => {
  description.setCustomValidity('');
  result.hidden = true;
});
document.querySelector('#service-grid').addEventListener('click', event => {
  const link = event.target.closest('[data-service]');
  if (!link) return;
  select.value = link.dataset.service;
  updateEstimate();
});

document.querySelector('#brief-form').addEventListener('submit', event => {
  event.preventDefault();
  const task = description.value.trim();
  if (!task) {
    description.setCustomValidity('Опишите задачу.');
    description.reportValidity();
    return;
  }
  const service = services.find(item => item.id === select.value);
  briefText.value = [`Проект: ${service.name}`, `Ориентир: ${priceLabel(service)}`, '', 'Задача:', task].join('\n');
  result.hidden = false;
  briefStatus.textContent = '';
  briefText.focus();
});

document.querySelector('#copy-brief').addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(briefText.value);
    briefStatus.textContent = 'Бриф скопирован.';
  } catch {
    briefText.focus();
    briefText.select();
    briefStatus.textContent = 'Текст выделен. Скопируйте его вручную или скачайте файл.';
  }
});

document.querySelector('#download-brief').addEventListener('click', () => {
  const url = URL.createObjectURL(new Blob([briefText.value], { type: 'text/plain;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'signal-brief.txt';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  briefStatus.textContent = 'Файл брифа подготовлен.';
});

if (contactUrl) {
  const contact = document.querySelector('#send-brief');
  contact.href = contactUrl;
  contact.hidden = false;
}

const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
const demoButton = document.querySelector('#run-demo');
const demoStatus = document.querySelector('#demo-status');
const demoSteps = [...document.querySelectorAll('#demo-steps li')];
demoButton.addEventListener('click', async () => {
  demoButton.disabled = true;
  demoSteps.forEach(step => step.classList.remove('done'));
  demoStatus.textContent = 'Сценарий запущен';
  for (const step of demoSteps) {
    if (!reducedMotion.matches) await new Promise(resolve => setTimeout(resolve, 450));
    step.classList.add('done');
  }
  demoStatus.textContent = 'Готово. Заявка зарегистрирована в демо-CRM.';
  demoButton.disabled = false;
  demoButton.firstChild.textContent = 'Повторить сценарий ';
});

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
