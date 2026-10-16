<?= $this->extend('layouts/dashboard') ?>

<?= $this->section('styles') ?>
<link rel="stylesheet" href="/assets/draw/css/draw.css">
<?= $this->endSection() ?>

<?= $this->section('content') ?>
<section class="draw-page">
    <div class="draw-heading">
        <div class="section-label">DRAW</div>
        <h2>Новая игра</h2>
        <p>Модуль Draw готов к подключению игровой механики.</p>
    </div>

    <div class="draw-card">
        <h3>Добро пожаловать в Draw</h3>
        <p>Здесь будет размещён игровой экран нового модуля.</p>
    </div>
</section>
<?= $this->endSection() ?>
