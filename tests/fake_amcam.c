/* Synthetic SDK for ABI/stream lifecycle tests; never accesses USB. */
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <pthread.h>
#include <unistd.h>
typedef struct {unsigned width,height;} Resolution;
typedef struct {const char *name;uint64_t flag;unsigned maxspeed,preview,still,maxfanspeed,ioctrol;float xpixsz,ypixsz;Resolution res[16];} Model;
typedef struct {char displayname[64],id[64];const Model *model;} Device;
typedef struct {unsigned width,height,flag,seq;uint64_t timestamp;} FrameInfo;
static Model model={.name="MU300",.preview=1,.res={{512,384}}};
static pthread_t thread;static volatile int running=0;static int started=0;
static void (*callback)(unsigned,void*);static void *context;
static int mode(const char *s){const char *m=getenv("TINY2_FAKE_AMCAM_SCENARIO");return m && strcmp(m,s)==0;}
const char *Amcam_Version(void){return "synthetic-sdk-1";}
unsigned Amcam_EnumV2(Device *d){memset(d,0,sizeof(*d));strcpy(d->displayname,"MU300 (Testbild)");strcpy(d->id,"test-mu300");d->model=&model;return 1;}
const Model *Amcam_get_Model(unsigned short v,unsigned short p){return v==0x0547 && p==0x6310 ? &model : NULL;}
void *Amcam_Open(const char *id){return mode("busy") || strcmp(id,"test-mu300")!=0 ? NULL : &model;}
int Amcam_get_Size(void *h,int *w,int *y){*w=512;*y=384;return 0;}
int Amcam_get_FinalSize(void *h,int *w,int *y){return Amcam_get_Size(h,w,y);}
int Amcam_put_Option(void *h,unsigned option,int value){return 0;}
int Amcam_put_RealTime(void *h,int n){return 0;}
int Amcam_PullImageWithRowPitchV2(void *h,void *buffer,int bits,int stride,FrameInfo *info){
 unsigned char *b=buffer;for(int y=0;y<384;y++)for(int x=0;x<512;x++){
  b[y*stride+x*3]=x<256?240:20;b[y*stride+x*3+1]=y<192?40:180;b[y*stride+x*3+2]=x<256?30:230;
 }
 *info=(FrameInfo){512,384,1,1,1000};return 0;
}
static void *frames(void *unused){unsigned count=0;while(running){usleep(70000);if(!running)break;
 if(mode("disconnect") && count++==3){callback(0x81,context);break;}
 callback(4,context);}return NULL;}
int Amcam_StartPullModeWithCallback(void *h,void (*cb)(unsigned,void*),void *ctx){
 if(mode("start-error"))return (int)0x80004005;
 callback=cb;context=ctx;running=1;started=1;return pthread_create(&thread,NULL,frames,NULL);
}
int Amcam_Stop(void *h){running=0;if(started){pthread_join(thread,NULL);started=0;}return 0;}
void Amcam_Close(void *h){Amcam_Stop(h);}
