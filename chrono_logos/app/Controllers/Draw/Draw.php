<?php

namespace App\Controllers\Draw;

use App\Controllers\BaseController;

class Draw extends BaseController
{
    public function getIndex()
    {
        return view('Draw/index', [
            'title' => 'Draw',
        ]);
    }
}
