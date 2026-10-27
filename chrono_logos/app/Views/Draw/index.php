<?= $this->extend('layouts/dashboard') ?>

<?= $this->section('styles') ?>
<link rel="stylesheet" href="/assets/draw/css/draw.css">
<?= $this->endSection() ?>

<?= $this->section('content') ?>
<section class="draw-page">
    <div class="draw-heading">
        <div class="section-label">DRAW</div>
        <h2>Draw — в разработке</h2>
        <p>Игровая механика этого модуля ещё не подключена. Сейчас здесь нельзя создать или запустить игру.</p>
    </div>

    <div class="draw-card">
        <h3>Во что можно сыграть сейчас?</h3>
        <p>В каталоге доступны готовые хронологические игры. Выберите игру и создайте комнату для участников.</p>
        <a class="primary-action" href="/games">Открыть каталог игр</a>
    </div>
</section>
<?= $this->endSection() ?>
