@echo off
set "PATH=C:\login and logout\desktop\src-tauri\target\debug;C:\Users\subha\.cargo\bin;C:\Users\subha\AppData\Local\Microsoft\WinGet\Packages\MartinStorsjo.LLVM-MinGW.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe\llvm-mingw-20261020-ucrt-x86_64\bin;%PATH%"
cd desktop\src-tauri
cargo test -- --nocapture
