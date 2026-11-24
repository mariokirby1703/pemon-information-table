import { Router } from '@angular/router';

const datasets: {path: string; label: string; title?: string}[] = [
  { path: '/', label: 'Rated Pemons' },
  { path: '/unrated-pemons', label: 'Unrated Pemons', title: 'Hyped · Unrated platformer demons' },
  { path: '/demons', label: 'Demons' }
];

/** Mount once per grid footer, then synchronize the active route. */
export function renderDatasetTabs(panel: HTMLElement, router: Router, activePath: string): void {
  let group = panel.querySelector<HTMLElement>('.dataset-tabs');
  if (!group) {
    group = document.createElement('nav');
    group.className = 'dataset-tabs';
    group.setAttribute('aria-label', 'Level datasets');
    for (const dataset of datasets) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = dataset.label;
      button.dataset['path'] = dataset.path;
      if (dataset.title) button.title = dataset.title;
      button.addEventListener('click', () => {
        if (button.getAttribute('aria-current') !== 'page') {
          void router.navigateByUrl(dataset.path);
        }
      });
      group.appendChild(button);
    }
    panel.appendChild(group);
  }
  for (const button of Array.from(group.querySelectorAll<HTMLButtonElement>('button'))) {
    if (button.dataset['path'] === activePath) {
      button.setAttribute('aria-current', 'page');
    } else {
      button.removeAttribute('aria-current');
    }
  }
}
