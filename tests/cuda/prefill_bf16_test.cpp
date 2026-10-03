#include "strata/prefill/gemm.hpp"
#include <cuda_runtime.h>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>

static void ck(cudaError_t e) { if (e != cudaSuccess) throw std::runtime_error(cudaGetErrorString(e)); }
static uint16_t bf(float x) { uint32_t u; std::memcpy(&u,&x,4); u += 0x7fff+((u>>16)&1); return (uint16_t)(u>>16); }
static float fp(uint16_t h) { uint32_t u=(uint32_t)h<<16; float x; std::memcpy(&x,&u,4); return x; }
template<class T> struct Dev {
    T* p=nullptr; size_t n;
    explicit Dev(size_t count):n(count) { ck(cudaMalloc((void**)&p,n*sizeof(T))); }
    ~Dev() { cudaFree(p); }
    void put(const std::vector<T>& x) { ck(cudaMemcpy(p,x.data(),n*sizeof(T),cudaMemcpyHostToDevice)); }
    std::vector<T> get() { std::vector<T> h(n); ck(cudaMemcpy(h.data(),p,n*sizeof(T),cudaMemcpyDeviceToHost)); return h; }
};

static void run(const char* name,int t,int n,int k,int pad,float beta,int special,bool expect_fast) {
    std::vector<uint16_t> x((size_t)t*k), w((size_t)n*k);
    uint32_t state=0x4175u;
    auto rnd=[&] { state=1664525u*state+1013904223u; return ((int)(state>>8)%1023-511)/256.0f; };
    for(int r=0;r<t;++r) for(int c=0;c<k;++c) x[(size_t)r*k+c]=bf(std::ldexp(rnd(),r%9-4));
    for(int r=0;r<n;++r) for(int c=0;c<k;++c) w[(size_t)r*k+c]=bf(std::ldexp(rnd(),r%7-3));
    if(special==1) x[k+1]=bf(1e-35f); // exact conversion must reject a wide-range activation row
    if(special==2) w[k+1]=bf(1e-35f); // weight rejection must preserve the full BF16 call
    if(special==3) std::fill(x.begin(),x.end(),uint16_t(0));
    if(special==4) x[0]=0x7fc1; // NaN: fallback, not accidental saturation
    if(special==5) {
        std::fill(x.begin(),x.end(),bf(std::ldexp(1.0f,-130)));
        std::fill(w.begin(),w.end(),bf(std::ldexp(1.0f,120)));
    }
    if(special==6 || special==7) for(int r=(special==6?1:0);r<t;++r) x[(size_t)r*k]=bf(1e-35f);
    if(special==8) {
        std::fill(x.begin(),x.end(),uint16_t(0)); std::fill(w.begin(),w.end(),uint16_t(0));
        for(int r=0;r<t;++r) { x[(size_t)r*k]=bf(1.f); x[(size_t)r*k+1]=bf(std::ldexp(1.f,-33)); }
        for(int r=0;r<n;++r) w[(size_t)r*k+1]=bf(std::ldexp(1.f,33));
    }
    const int ld=n+pad;
    std::vector<float> initial((size_t)t*ld,123.25f);
    for(int r=0;r<t;++r) for(int c=0;c<n;++c) initial[(size_t)r*ld+c]=rnd();
    Dev<uint16_t> dx(x.size()),dw(w.size()); Dev<float> dy(initial.size()); dx.put(x);dw.put(w);
    cudaStream_t s;ck(cudaStreamCreate(&s));
    {
        strata::prefill::Gemm gm; std::string err;
        if(!gm.init(s,32ll<<20,err)) throw std::runtime_error(err);
        auto invoke=[&](bool fast) {
            dy.put(initial); strata::prefill::Gemm::set_turing_bf16(fast);
            gm.bf16(dx.p,dw.p,dy.p,t,n,k,ld,beta); ck(cudaStreamSynchronize(s));return dy.get();
        };
        auto old=invoke(false), candidate=invoke(true);
        double maxdiff=0,scale=0;
        for(int r=0;r<t;++r) for(int c=0;c<ld;++c) {
            const size_t i=(size_t)r*ld+c;
            if(c>=n) {if(candidate[i]!=initial[i]) throw std::runtime_error("stride padding overwritten");continue;}
            if(!std::isfinite(old[i])||!std::isfinite(candidate[i])) {
                if(!(std::isnan(old[i])&&std::isnan(candidate[i])) && old[i]!=candidate[i]) throw std::runtime_error("nonfinite mismatch");
                continue;
            }
            maxdiff=std::max(maxdiff,(double)std::abs(old[i]-candidate[i]));scale=std::max(scale,(double)std::abs(old[i]));
        }
        if(maxdiff>std::max(1e-5,scale*2e-5)) throw std::runtime_error("BF16 baseline error too large");
        double maxref=0,oldref=0;
        for(int q=0;q<48;++q) {
            int r=(q*137)%t,c=(q*191)%n;
            double ref=beta*initial[(size_t)r*ld+c],mag=std::abs(ref);
            for(int j=0;j<k;++j) {double v=(double)fp(x[(size_t)r*k+j])*fp(w[(size_t)c*k+j]);ref+=v;mag+=std::abs(v);}
            if(!std::isfinite(ref))continue;
            double rel=std::abs(candidate[(size_t)r*ld+c]-ref)/std::max(mag,1e-20);
            maxref=std::max(maxref,rel);oldref=std::max(oldref,std::abs(old[(size_t)r*ld+c]-ref)/std::max(mag,1e-20));
            if(rel>3e-6) throw std::runtime_error("FP64 reference error too large");
        }
        if(expect_fast && gm.fast_tiles()==0) throw std::runtime_error("fast path not exercised");
        if((special==1||special==2||special==4||special==6||special==7) && gm.fallback_tiles()==0) throw std::runtime_error("fallback not exercised");
        std::printf("PASS %s T%d N%d K%d beta%.0f: diff/scale %.3g; FP64 error/absolute-product-sum old %.3g new %.3g; fast %lld fallback %lld\n",
            name,t,n,k,beta,maxdiff/std::max(scale,1e-20),oldref,maxref,(long long)gm.fast_tiles(),(long long)gm.fallback_tiles());
    }
    ck(cudaStreamDestroy(s));
}

static void bench(int t,int n,int k) {
    std::vector<uint16_t> x((size_t)t*k),w((size_t)n*k);
    for(size_t i=0;i<x.size();++i)x[i]=bf(((int)(i*97%509)-254)/256.f);
    for(size_t i=0;i<w.size();++i)w[i]=bf(((int)(i*113%511)-255)/256.f);
    Dev<uint16_t> dx(x.size()),dw(w.size());Dev<float> dy((size_t)t*n);dx.put(x);dw.put(w);
    cudaStream_t s;ck(cudaStreamCreate(&s));
    {
        strata::prefill::Gemm gm;std::string err;if(!gm.init(s,32ll<<20,err))throw std::runtime_error(err);
        double times[2]={};
        for(int mode=0;mode<2;++mode) {
            strata::prefill::Gemm::set_turing_bf16(mode!=0);
            gm.bf16(dx.p,dw.p,dy.p,t,n,k);ck(cudaStreamSynchronize(s));
            auto a=std::chrono::steady_clock::now();
            for(int i=0;i<5;++i)gm.bf16(dx.p,dw.p,dy.p,t,n,k);
            ck(cudaStreamSynchronize(s));
            times[mode]=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-a).count()/5;
        }
        std::printf("BENCH T%d N%d K%d: %.3f -> %.3f ms (%.2fx) fast %lld fallback %lld\n",t,n,k,times[0],times[1],times[0]/times[1],(long long)gm.fast_tiles(),(long long)gm.fallback_tiles());
    }
    ck(cudaStreamDestroy(s));
}
int main(int argc,char**) {
    try {
        cudaDeviceProp prop;ck(cudaGetDeviceProperties(&prop,0));
        if(prop.major!=7||prop.minor!=5){std::puts("SKIP: Turing device required");return 0;}
        run("down",257,320,10240,3,0,0,true);
        run("up-tail-beta",2051,10240,320,7,1,0,true);
        run("activation-fallback",1027,320,10240,5,1,1,true);
        run("weight-fallback",128,320,10240,3,0,2,false);
        run("zero",128,320,10240,1,0,3,true);
        run("nonfinite",128,320,10240,1,0,4,false);
        run("subnormal",128,320,10240,1,0,5,true);
        run("half-subnormal-product",128,320,10240,1,0,8,true);
        run("up-partial-fallback",4097,10240,320,3,0,6,true);
        run("all-row-fallback",128,320,10240,3,1,7,false);
        run("up-long-tail",16385,10240,320,3,0,0,true);
        run("short-bypass",127,320,10240,3,1,0,false);
        run("shape-bypass",257,129,320,7,0,0,false);
        if(argc>1)for(int t:{1024,8192,16384}){bench(t,320,10240);bench(t,10240,320);}
        std::puts("FAILURES: 0");return 0;
    }catch(const std::exception&e){std::fprintf(stderr,"FAIL: %s\n",e.what());return 1;}
}
