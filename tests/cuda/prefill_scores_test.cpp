#include "strata/kernels/qsa_select.hpp"
#include <cuda_runtime.h>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <random>
#include <stdexcept>
#include <vector>
namespace k=strata::kernels;
static void ck(cudaError_t e){if(e!=cudaSuccess)throw std::runtime_error(cudaGetErrorString(e));}
template<class T>struct Dev{T*p=nullptr;size_t n;explicit Dev(size_t m):n(m){ck(cudaMalloc((void**)&p,n*sizeof(T)));}~Dev(){cudaFree(p);}void put(const std::vector<T>&v){ck(cudaMemcpy(p,v.data(),n*sizeof(T),cudaMemcpyHostToDevice));}std::vector<T>get(){std::vector<T>v(n);ck(cudaMemcpy(v.data(),p,n*sizeof(T),cudaMemcpyDeviceToHost));return v;}};
static void run(int ctx,int capacity,int nq){
    auto s=k::qsa_real_shapes();int mb=capacity/4+2;
    // Deliberately omit the final tail key: the scorer must use dead for it.
    std::vector<float>p((size_t)(ctx/4)*128),dead(128),q((size_t)nq*512),initial((size_t)nq*mb,-123.f);
    std::mt19937 rng(185);std::normal_distribution<float>d(0.f,1.f);for(auto&v:p)v=d(rng);for(auto&v:q)v=d(rng);for(auto&v:dead)v=d(rng);
    std::vector<int32_t>st((size_t)nq*k::kStepCount);
    for(int i=0;i<nq;++i){int cells=ctx-nq+((ctx&1)?nq-1-i:i)+1;auto*x=st.data()+(size_t)i*k::kStepCount;x[k::kStepNKv]=cells;x[k::kStepNBid]=cells/4;}
    Dev<float>dp(p.size()),dd(dead.size()),dq(q.size()),out(initial.size());Dev<int32_t>dt(st.size());dp.put(p);dd.put(dead);dq.put(q);dt.put(st);
    auto launch=[&](int tile){k::qsa_set_score_tile(tile);k::qsa_block_scores(dp.p,dd.p,dq.p,dt.p,nq,mb,s,out.p,nullptr,ctx/4+1);};
    out.put(initial);launch(0);ck(cudaDeviceSynchronize());auto original=out.get();
    float times[3];int modes[3]={0,4,8};
    cudaEvent_t e0,e1;ck(cudaEventCreate(&e0));ck(cudaEventCreate(&e1));
    for(int m=0;m<3;++m){
        out.put(initial);launch(modes[m]);ck(cudaDeviceSynchronize());auto now=out.get();
        if(std::memcmp(original.data(),now.data(),now.size()*sizeof(float)))throw std::runtime_error("scores not bitwise identical");
        ck(cudaEventRecord(e0));for(int j=0;j<10;++j)launch(modes[m]);ck(cudaEventRecord(e1));ck(cudaEventSynchronize(e1));ck(cudaEventElapsedTime(&times[m],e0,e1));times[m]/=10;
    }
    double error=0;
    for(int i=0;i<std::min(16,nq);++i){int cells=st[(size_t)i*k::kStepCount+k::kStepNKv],nb=cells/4;
        for(int b:{0,nb/2,nb}){const float*key=b==nb?dead.data():p.data()+(size_t)b*128;double sum=0,mag=0;
            for(int h=0;h<4;++h){double dot=0;for(int j=0;j<128;++j){double v=(double)key[j]*q[(size_t)i*512+h*128+j];dot+=v;mag+=std::abs(v);}sum+=std::max(0.0,dot);}
            if(b==nb&&cells%4){sum+=1e9;mag+=1e9;}
            error=std::max(error,std::abs(original[(size_t)i*mb+b]-sum)/std::max(mag,1e-20));
        }}
    if(error>1e-6)throw std::runtime_error("FP64 score reference mismatch");
    ck(cudaEventDestroy(e0));ck(cudaEventDestroy(e1));
    std::printf("PASS scores ctx%d capacity%d queries%d: bitwise 0/4/8 incl untouched tail, FP64 %.3g; %.3f / %.3f / %.3f ms\n",ctx,capacity,nq,error,times[0],times[1],times[2]);
}
int main(){try{run(1025,262144,1);run(2039,262144,33);run(31243,32768,256);run(65536,262144,256);run(130048,262144,256);run(262144,262144,256);run(262143,262144,257);std::puts("FAILURES: 0");return 0;}catch(const std::exception&e){std::fprintf(stderr,"FAIL: %s\n",e.what());return 1;}}
