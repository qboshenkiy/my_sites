<?php
require __DIR__ . '/../app/Libraries/TimelineImport.php';
use App\Libraries\TimelineImport;

function check(bool $condition, string $message): void {
    if (!$condition) throw new RuntimeException($message);
}
$sample = TimelineImport::parse(file_get_contents(__DIR__ . '/../app/Data/genesis-50.json'));
check(count($sample['cards']) === 50, 'Expected 50 chapters');
foreach ($sample['cards'] as $i => $card) {
    check((int) $card['sort_order'] === $i + 1, 'Narrative order');
    check(str_starts_with($card['revealed_value'], 'Бытие ' . ($i + 1) . ':'), 'Chapter reference');
}
$base = ['title' => 'Test', 'cards' => [['title' => 'Event', 'sort_order' => '-1.25']]];
check(TimelineImport::parse(json_encode($base))['cards'][0]['is_enabled'] === true, 'Default selection');
$after = TimelineImport::appendAfter([['sort_order' => '5'], ['sort_order' => '-1'], ['sort_order' => '2']], 50);
check(array_column($after, 'sort_order') === ['51', '52', '53'], 'Append new book after existing cards');
$precise = TimelineImport::appendAfter([['sort_order'=>'99999999999999.000002','label'=>'later'],['sort_order'=>'99999999999999.000001','label'=>'earlier']], 50);
check(array_column($precise,'label') === ['earlier','later'], 'Exact decimal sorting without floating point loss');
foreach ([
    '{',
    json_encode(['title' => 'Test', 'cards' => []]),
    json_encode(['title' => 'Test', 'cards' => [['title' => '', 'sort_order' => 1]]]),
    json_encode(['title' => 'Test', 'cards' => [['title' => 'Event', 'sort_order' => '1e30']]]),
    json_encode(['title' => 'Test', 'cards' => [['title' => 'Event', 'sort_order' => 1, 'is_enabled' => 'false']]]),
    json_encode(['title' => 'Test', 'cards' => [['title' => 'Event', 'sort_order' => 1, 'difficulty' => 'invalid']]]),
    json_encode(['title' => 'Test', 'cards' => array_fill(0, 1001, $base['cards'][0])]),
    str_repeat(' ', TimelineImport::MAX_BYTES + 1),
] as $input) {
    try { TimelineImport::parse($input); throw new RuntimeException('Invalid import accepted'); }
    catch (InvalidArgumentException $expected) {}
}
echo "PASS: Genesis 50 chapter coverage, import bounds and validation\n";
