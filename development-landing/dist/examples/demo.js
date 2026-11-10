const basket = document.querySelector('#basket');
if (basket) {
  let count = 0;
  let total = 0;
  document.querySelectorAll('[data-price]').forEach(button => button.onclick = () => {
    count += 1;
    total += Number(button.dataset.price);
    basket.textContent = 'Позиций: ' + count + ' · ' + total + ' сом';
  });
  document.querySelector('#clear-basket').onclick = () => {
    count = total = 0;
    basket.textContent = 'Корзина пуста.';
  };
  document.querySelectorAll('[data-filter]').forEach(button => button.onclick = () => {
    document.querySelectorAll('[data-filter]').forEach(filter => filter.setAttribute('aria-pressed', String(filter === button)));
    document.querySelectorAll('[data-category]').forEach(tile => {
      tile.hidden = button.dataset.filter !== 'all' && button.dataset.filter !== tile.dataset.category;
    });
  });
}
const booking = document.querySelector('#booking');
document.querySelectorAll('[data-slot]').forEach(button => button.onclick = () => {
  booking.textContent = 'Вы выбрали: ' + button.dataset.slot + '. Это пробная запись.';
});
const quote = document.querySelector('#quote');
if (quote) {
  const device = document.querySelector('#device');
  const service = document.querySelector('#service');
  const update = () => quote.textContent = 'От ' + Math.round(Number(device.value) * Number(service.value)) + ' сом';
  device.onchange = service.onchange = update;
  update();
}
