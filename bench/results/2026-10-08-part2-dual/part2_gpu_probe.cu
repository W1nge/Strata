#include <cuda_runtime.h>
#include <cstdio>
__global__ void check(int* p){p[threadIdx.x]=threadIdx.x*3+7;}
int main(){int n=0;auto e=cudaGetDeviceCount(&n);printf("count=%d status=%s\n",n,cudaGetErrorString(e));if(e!=cudaSuccess)return 1;
for(int d=0;d<n;++d){cudaDeviceProp p{};cudaGetDeviceProperties(&p,d);cudaSetDevice(d);int* ptr=nullptr;int h[32]={};e=cudaMalloc(&ptr,sizeof h);if(e!=cudaSuccess)return 2;check<<<1,32>>>(ptr);e=cudaDeviceSynchronize();if(e!=cudaSuccess){printf("device=%d launch=%s\n",d,cudaGetErrorString(e));return 3;}cudaMemcpy(h,ptr,sizeof h,cudaMemcpyDeviceToHost);for(int i=0;i<32;++i)if(h[i]!=i*3+7)return 4;cudaFree(ptr);printf("device=%d name=%s sm=%d%d VRAM=%zu kernel=PASS\n",d,p.name,p.major,p.minor,p.totalGlobalMem);for(int j=0;j<n;++j)if(j!=d){int peer=0;cudaDeviceCanAccessPeer(&peer,d,j);printf("peer %d -> %d = %d\n",d,j,peer);}}
return n==2?0:5;}
