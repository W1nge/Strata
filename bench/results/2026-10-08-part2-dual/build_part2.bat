@echo off
call "C:\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
set PATH=E:\strata-setup\cuda-portable\bin;%PATH%
set VSLANG=1033
set TEMP=E:\strata-setup\part2-dual\temp
set TMP=E:\strata-setup\part2-dual\temp
set PART2_CMAKE=C:\Users\Winge\AppData\Roaming\Python\Python313\site-packages\cmake\data\bin\cmake.exe
nvcc -allow-unsupported-compiler -std=c++17 -Xcompiler /MD --cudart shared -gencode arch=compute_60,code=sm_60 -gencode arch=compute_75,code=sm_75 C:/Users/Winge/Documents/Playground/part2_gpu_probe.cu -o E:/strata-setup/part2-dual/gpu_probe.exe
if errorlevel 1 exit /b 1
E:\strata-setup\part2-dual\gpu_probe.exe
if errorlevel 1 exit /b 1
%PART2_CMAKE% -S C:/Users/Winge/Documents/Playground/Strata-optimization-pr -B E:/strata-setup/part2-dual/build -G Ninja -DCMAKE_MAKE_PROGRAM=C:/Users/Winge/AppData/Roaming/Python/Python313/Scripts/ninja.exe -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_RUNTIME_LIBRARY=Shared -DSTRATA_ENABLE_CUDA=ON -DSTRATA_EXPERIMENTAL_SM60=ON -DCMAKE_CUDA_COMPILER=E:/strata-setup/cuda-portable/bin/nvcc.exe -DCMAKE_CUDA_ARCHITECTURES="60-real;75-real" -DCMAKE_CUDA_FLAGS=-allow-unsupported-compiler -DSTRATA_NATIVE_EXPERTS=ON -DSTRATA_GGML_DIR=C:/Users/Winge/.zcode/workspace/default/llama.cpp-oracle -DSTRATA_BUILD_TESTS=ON
if errorlevel 1 exit /b 1
%PART2_CMAKE% --build E:/strata-setup/part2-dual/build --target strata -j 4
