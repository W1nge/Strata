#include "strata/kernels/qsa_select.hpp"
#include <cuda_runtime.h>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <limits>
#include <numeric>
#include <random>
#include <stdexcept>
#include <vector>
namespace k=strata::kernels;
static void ck(cudaError_t e){if(e!=cudaSuccess)throw std::runtime_error(cudaGetErrorString(e));}
static uint32_t key(float x){x+=0.f;if(std::isnan(x))return 0;uint32_t u;std::memcpy(&u,&x,4);return u&0x80000000u?~u:u|0x80000000u;}
template<class T>struct Dev{T*p=nullptr;size_t n;explicit Dev(size_t m):n(m){ck(cudaMalloc((void**)&p,n*sizeof(T)));}~Dev(){cudaFree(p);}void put(const std::vector<T>&v){ck(cudaMemcpy(p,v.data(),n*sizeof(T),cudaMemcpyHostToDevice));}std::vector<T>get(){std::vector<T>v(n);ck(cudaMemcpy(v.data(),p,n*sizeof(T),cudaMemcpyDeviceToHost));return v;}};
static void run(int ctx,int capacity,int nq,int pattern){
    auto s=k::qsa_real_shapes();int mb=capacity/4+2,cap=(int)k::qsa_selection_width(k::kTopkMaxCells,s);
    std::vector<int32_t>st((size_t)nq*k::kStepCount),initial((size_t)nq*cap,-77);
    std::vector<float>sc((size_t)nq*mb);std::mt19937 rng(521);std::normal_distribution<float>d(15.f,3.f);
    for(int q=0;q<nq;++q){
        int cells=ctx-nq+q+1;auto*p=st.data()+(size_t)q*k::kStepCount;
        p[k::kStepNKv]=cells;p[k::kStepNBid]=cells/4;p[k::kStepWidth]=(int)k::qsa_selection_width(cells,s);
        for(int b=0;b<mb;++b){float v=pattern==1?1.f:pattern==2?float(b%17):d(rng);if(pattern==3){if(b%113==0)v=std::numeric_limits<float>::quiet_NaN();else if(b%127==0)v=-0.f;else if(b%137==0)v=std::numeric_limits<float>::infinity();else if(b%139==0)v=-std::numeric_limits<float>::infinity();}sc[(size_t)q*mb+b]=v;}
        if(pattern==0 && cells%4)sc[(size_t)q*mb+cells/4]=1e9f;
    }
    Dev<float> ds(sc.size());Dev<int32_t>dt(st.size()),out(initial.size());ds.put(sc);dt.put(st);
    const int active=ctx/4+1;
    auto launch=[&](bool wide){k::qsa_set_topk_wide(wide);k::qsa_block_topk(ds.p,dt.p,nq,mb,cap,s,out.p,nullptr,active);};
    out.put(initial);launch(false);ck(cudaDeviceSynchronize());auto a=out.get();
    out.put(initial);launch(true);ck(cudaDeviceSynchronize());auto b=out.get();
    if(a!=b)throw std::runtime_error("selection differs from baseline");
    for(int q=0;q<std::min(nq,17);++q){
        int cells=st[(size_t)q*k::kStepCount+k::kStepNKv],width=st[(size_t)q*k::kStepCount+k::kStepWidth];
        std::vector<int> blocks((cells+3)/4);std::iota(blocks.begin(),blocks.end(),0);
        std::sort(blocks.begin(),blocks.end(),[&](int i,int j){auto x=key(sc[(size_t)q*mb+i]),y=key(sc[(size_t)q*mb+j]);return x!=y?x>y:i<j;});
        std::vector<int> expected;for(int block:blocks){for(int j=block*4;j<std::min(cells,block*4+4)&&int(expected.size())<width;++j)expected.push_back(j);if(int(expected.size())==width)break;}
        std::sort(expected.begin(),expected.end());if(!std::equal(expected.begin(),expected.end(),b.begin()+(size_t)q*cap))throw std::runtime_error("CPU selection mismatch");
        for(int j=width;j<cap;++j)if(b[(size_t)q*cap+j]!=-77)throw std::runtime_error("selection tail overwritten");
    }
    cudaEvent_t e0,e1;ck(cudaEventCreate(&e0));ck(cudaEventCreate(&e1));float ms[2];
    for(int mode=0;mode<2;++mode){launch(mode!=0);ck(cudaEventRecord(e0));for(int r=0;r<10;++r)launch(mode!=0);ck(cudaEventRecord(e1));ck(cudaEventSynchronize(e1));ck(cudaEventElapsedTime(&ms[mode],e0,e1));ms[mode]/=10;}
    ck(cudaEventDestroy(e0));ck(cudaEventDestroy(e1));
    std::printf("PASS topk ctx%d capacity%d queries%d pattern%d: exact IDs incl CPU; %.3f -> %.3f ms (%.2fx)\n",ctx,capacity,nq,pattern,ms[0],ms[1],ms[0]/ms[1]);
}
int main(){try{
    run(1024,262144,17,1);run(31243,32768,256,0);run(31243,262144,256,0);run(130048,262144,256,0);run(262144,262144,256,0);
    for(int p=1;p<=3;++p)run(262144,262144,17,p);
    run(135168,262144,17,2);run(135172,262144,17,2);run(266240,270000,17,2);run(266244,270000,17,2);
    std::puts("FAILURES: 0");return 0;
}catch(const std::exception&e){std::fprintf(stderr,"FAIL: %s\n",e.what());return 1;}}
