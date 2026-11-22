"""Plot the prioritized 1 KiB/two-pair RSS and live-payload observations."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
VERSIONS=['v2.1.2','v3.5.0','v3.5.3','v3.6.0','v3.6.1','v3.7.0']
COLORS=['#64748b','#159895','#d58322','#6143b8','#d52c59','#0072b2']
def main():
    rows=[json.loads(p.read_text()) for p in sorted((ROOT/'results/release-v370-v1/concurrent/measured').glob('*.json'))]
    assert len(rows)==126 and all(r['valid'] for r in rows)
    rows=[r for r in rows if r['config']['size']==1024 and r['config']['pairs']==2]
    assert len(rows)==18
    fig,axes=plt.subplots(1,3,figsize=(15,4.8))
    for v,color in zip(VERSIONS,COLORS):
        for i,r in enumerate(x for x in rows if x['config']['version']==v):
            duration=r['final']['elapsed_ns']/1e9
            samples=[s for s in r['samples'] if s['progress']['elapsed_ns']/1e9<=duration]
            xs=[s['progress']['elapsed_ns']/1e9 for s in samples]
            for ax,key in [(axes[0],'rss'),(axes[1],'live')]:
                ys=[s['memory']['VmRSS']/2**20 if key=='rss' else s['progress']['live_estimate_bytes']/2**20 for s in samples]
                ax.plot(xs,ys,color=color,alpha=.65,lw=.9,label=v if i==0 else None)
            pts=r['checkpoints'][1:]
            axes[2].plot([p['t']-pts[0]['t'] for p in pts],[p['Rss']/2**20 for p in pts],color=color,alpha=.65,lw=.9,marker='.',label=v if i==0 else None)
    for ax,title in zip(axes,['Working process RSS','Working live payload (estimate)','RSS after completion']):
        ax.set_title(title);ax.set_ylabel('MiB');ax.set_ylim(bottom=0);ax.grid(alpha=.2)
    axes[0].set_xlabel('Seconds since work started');axes[1].set_xlabel('Seconds since work started')
    axes[2].set_xlabel('Seconds since completion observed')
    axes[1].axhline(128,color='black',ls=':',lw=.8,label='Payload cap')
    axes[0].legend(fontsize=8)
    fig.suptitle('1 KiB, 2 pairs, 128 MiB cap | upstream defaults | all 3 runs per version\nRSS and payload are different quantities; idle starts after all objects are freed.')
    fig.tight_layout()
    out=ROOT/'docs/v370';out.mkdir(parents=True,exist_ok=True)
    fig.savefig(out/'memory-1k.png',dpi=160);fig.savefig(out/'memory-1k.svg');plt.close(fig)

if __name__=='__main__':main()
