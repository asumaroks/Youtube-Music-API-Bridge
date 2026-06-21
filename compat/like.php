<?php
declare(strict_types=1);

/*
 * Compatibility entrypoint.
 * ytm_like.py chooses YouTube Music Desktop API on Windows when the exact
 * installed executable is running; otherwise it uses the existing provider.
 */

$project = getenv('YTM_LIKE_PROJECT') ?: 'C:\scripts\YoutubeMusicAPI';
$script = $project . DIRECTORY_SEPARATOR . 'ytm_like.py';
$venvPython = $project . DIRECTORY_SEPARATOR . '.venv' . DIRECTORY_SEPARATOR
    . (PHP_OS_FAMILY === 'Windows' ? 'Scripts\python.exe' : 'bin/python');
$python = is_file($venvPython)
    ? $venvPython
    : (PHP_OS_FAMILY === 'Windows' ? 'python.exe' : 'python3');

if (!is_file($script)) {
    fwrite(STDERR, "ERROR: Script not found: {$script}\n");
    exit(2);
}

$command = escapeshellarg($python) . ' ' . escapeshellarg($script) . ' like-current';
passthru($command, $exitCode);
exit($exitCode);
