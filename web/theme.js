// Run before styles load so a saved dark theme never flashes light first.
(() => {
  const key='race-atlas-theme',system=matchMedia('(prefers-color-scheme: dark)');
  let saved=null;
  try {saved=localStorage.getItem(key);} catch {}
  if(!['light','dark'].includes(saved))saved=null;
  function apply(theme){
    document.documentElement.dataset.theme=theme;
    document.querySelector('meta[name="theme-color"]').content=theme==='dark'?'#22212a':'#fafaf5';
    const button=document.querySelector('#theme-toggle');
    if(button){button.setAttribute('aria-pressed',String(theme==='dark'));button.title=`Switch to ${theme==='dark'?'light':'dark'} mode`;}
    document.dispatchEvent(new CustomEvent('themechange',{detail:theme}));
  }
  apply(saved||(system.matches?'dark':'light'));
  document.addEventListener('DOMContentLoaded',()=>{
    apply(document.documentElement.dataset.theme);
    document.querySelector('#theme-toggle')?.addEventListener('click',()=>{
      saved=document.documentElement.dataset.theme==='dark'?'light':'dark';
      try {localStorage.setItem(key,saved);} catch {}
      apply(saved);
    });
  });
  system.addEventListener('change',()=>{if(!saved)apply(system.matches?'dark':'light');});
  window.addEventListener('storage',event=>{
    if(event.key!==key&&event.key!==null)return;
    saved=['light','dark'].includes(event.newValue)?event.newValue:null;
    apply(saved||(system.matches?'dark':'light'));
  });
})();
