@echo off
chcp 65001 > nul
title ElevenLabs Automatic Narrator
echo ==================================================
echo Starting ElevenLabs Narrator in 100%% Automatic Mode...
echo Text file: scientific_test_1_quantum_cosmos.txt
echo Saving MP3 chunks to folder: TESTS
echo ==================================================
echo.

python elevenlabs_neuro_stealth_narrator.py --file scientific_test_1_quantum_cosmos.txt --out-dir TESTS --manual-ip

echo.
echo ==================================================
echo Execution completed or paused.
echo ==================================================
pause
