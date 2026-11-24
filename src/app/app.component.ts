import { renderDatasetTabs } from './dataset-tabs';
import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { AgGridAngular } from 'ag-grid-angular';
import { ColDef, RowStyle, RowClassParams } from 'ag-grid-community';
import { CartService } from './cart.service';
import { CookieService } from 'ngx-cookie-service';
import { HttpClient } from '@angular/common/http';
import { Router, NavigationEnd } from '@angular/router';
import { filter } from 'rxjs/operators';
import { Subscription } from 'rxjs';

@Component({
  selector: 'app-root',
  styleUrls: ['./app.component.css'],
  templateUrl: `./app.component.html`
})
export class AppComponent implements OnInit {
  private cookie_name = '';
  private all_cookies: any = '';
  public gridOptions: any = {};
  public pagination = true;
  public paginationPageSize = 100;
  public paginationPageSizeSelector: number[] | boolean = [10, 25, 50, 100, 150, 250, 500, 1000];
  public enableRowStyle = false;
  public isDemonsRoute = false;
  public isUnratedRoute = false;
  public loadError = '';
  private dataRequest?: Subscription;
  private currentAsset = '';

  constructor(private cartService: CartService, private cookieService: CookieService, private http: HttpClient, private cdr: ChangeDetectorRef, private router: Router) {}

  rowData: any[] = [];
  rawData: any[] = [];

  getRowStyle = (params: RowClassParams<any, any>): RowStyle | undefined => {
    if (this.enableRowStyle && params.data && params.data.ID) {
      return {
        backgroundImage: `url("https://levelthumbs.prevter.me/thumbnail/${params.data.ID}")`,
        backgroundSize: 'cover',
        backgroundRepeat: 'no-repeat',
        backgroundPosition: 'center',
        backgroundColor: 'rgba(0, 0, 0, 0.3)',
        backgroundBlendMode: 'darken',
        borderBottom: '2px solid #000'
      };
    }
    return undefined;
  };

  onGridReady(): void {
    // wenn das Grid DOM steht, baue Footer-UI
    this.updateCustomPaginationText();
  }

  ngOnInit(): void {
    this.gridOptions = {
      animateRows: true,
      getRowStyle: this.getRowStyle
    }
    this.router.events
        .pipe(filter((e): e is NavigationEnd => e instanceof NavigationEnd))
        .subscribe(e => this.selectDataset(e.urlAfterRedirects));

    this.cookie_name = this.cookieService.get('PHPSESSID');
    this.all_cookies = this.cookieService.getAll();
    this.selectDataset(this.router.url);
  }

  private selectDataset(url: string): void {
    const path = url.split(/[?#]/)[0];
    this.isDemonsRoute = path === '/demons';
    this.isUnratedRoute = path === '/unrated-pemons';
    if (this.isDemonsRoute) {
      this.dataRequest?.unsubscribe();
      this.currentAsset = '';
      return;
    }
    this.updateCustomPaginationText();
    const asset = this.isUnratedRoute ? 'unrated-pemons.json' : 'pemons.json';
    if (asset === this.currentAsset) return;
    this.currentAsset = asset;
    this.dataRequest?.unsubscribe();
    this.rowData = [];
    this.loadError = '';
    this.dataRequest = this.http.get<any[]>('assets/' + asset).subscribe({
      next: data => {
        this.rawData = Array.isArray(data) ? data.map(({ showcase, ...rest }) => rest) : [];
        this.rowData = [...this.rawData];
        this.updateCustomPaginationText();
        this.cdr.detectChanges();
      },
      error: error => {
        this.loadError = 'Could not load ' + asset;
        console.error(this.loadError, error);
        this.cdr.detectChanges();
      }
    });
  }


  setRowStyle(enabled: boolean): void {
    if (this.enableRowStyle === enabled) return;
    this.enableRowStyle = enabled;
    this.gridOptions?.api?.refreshCells({ force: true, columns: ['difficulty', 'rating'] });
    this.gridOptions?.api?.redrawRows();

    this.rowData = [...this.rowData];
    setTimeout(() => this.cdr.detectChanges(), 0);
  }

  toggleRowStyle(): void {
    this.setRowStyle(!this.enableRowStyle);
  }

  updateCustomPaginationText(): void {
    setTimeout(() => {
      const paginationPanel = document.querySelector('.pemon-grid .ag-paging-panel') as HTMLElement | null;
      if (!paginationPanel) return;

      // © Hinweis
      let customPaginationText = document.getElementById('customPaginationText') as HTMLSpanElement | null;
      if (!customPaginationText) {
        customPaginationText = document.createElement('span');
        customPaginationText.id = 'customPaginationText';
        customPaginationText.innerText = '© Developed by mariokirby1703 - Information gathered by mariokirby1703 and Lutz127';
        paginationPanel.insertBefore(customPaginationText, paginationPanel.firstChild);
      }

      // --- Row Style Toggle ---
      let toggleContainer = document.getElementById('toggleContainer') as HTMLDivElement | null;
      if (!toggleContainer) {
        toggleContainer = document.createElement('div');
        toggleContainer.id = 'toggleContainer';
        toggleContainer.className = 'switch-container';
        toggleContainer.innerHTML = `
    <label class="switch">
      <input type="checkbox" id="rowStyleToggle">  <!-- KEIN 'checked' hier -->
      <span class="slider round"></span>
    </label>
    <span class="switch-label">Row Style</span>
  `;
        paginationPanel.appendChild(toggleContainer);
      }

      // Zustand immer synchronisieren + Listener sauber setzen
      const rowStyleToggle = document.getElementById('rowStyleToggle') as HTMLInputElement | null;
      if (rowStyleToggle) {
        rowStyleToggle.checked = this.enableRowStyle;   // spiegelt aktuellen Zustand
        rowStyleToggle.onchange = (ev: Event) => {
          const input = ev.target as HTMLInputElement;
          this.setRowStyle(input.checked);              // <<— EXPLIZIT setzen
        };
      } else {
        // Bereits vorhanden? Zustand synchronisieren
        const rowStyleToggle = document.getElementById('rowStyleToggle') as HTMLInputElement | null;
        if (rowStyleToggle) rowStyleToggle.checked = this.enableRowStyle;
      }

      renderDatasetTabs(paginationPanel, this.router, this.isUnratedRoute ? '/unrated-pemons' : '/');
    }, 0);
  }

  // Utility function to convert seconds to dynamic time format (H:M:S)
  formatTime(seconds: number): string {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;

    if (hours > 0) {
      return `${hours}h ${minutes}m ${secs}s`;
    } else if (minutes > 0) {
      return `${minutes}m ${secs}s`;
    } else {
      return `${secs}s`;
    }
  }

  // Column Definitions: Defines the columns to be displayed.
  colDefs: ColDef[] = [
    { field: "number", flex: 1.4, minWidth: 85, cellStyle: { 'text-align': 'center' } },
    {
      field: "level",
      headerName: "Level Name",
      flex: 3.3,
      minWidth: 190,
      filter: true,
      comparator: (valueA: string, valueB: string) => {
        return valueA.toLowerCase().localeCompare(valueB.toLowerCase());
      }
      // showcase link logic removed – we just display the plain name
    },
    {
      field: "creator",
      flex: 2.5,
      minWidth: 150,
      filter: true,
      comparator: (valueA: string, valueB: string) => {
        return valueA.toLowerCase().localeCompare(valueB.toLowerCase());
      }
    },
    { field: "ID", flex: 1.8, minWidth: 110, headerName: "Level ID" },
    {
      field: "difficulty",
      flex: 2.4,
      minWidth: 140,
      filter: true,
      cellClassRules: {
        'easy': (p: any) => !this.enableRowStyle && p.data?.difficulty === 'Easy Demon',
        'medium': (p: any) => !this.enableRowStyle && p.data?.difficulty === 'Medium Demon',
        'hard': (p: any) => !this.enableRowStyle && p.data?.difficulty === 'Hard Demon',
        'insane': (p: any) => !this.enableRowStyle && p.data?.difficulty === 'Insane Demon',
        'extreme': (p: any) => !this.enableRowStyle && p.data?.difficulty === 'Extreme Demon',
      },
      comparator: (valueA: string, valueB: string) => {
        const order = ["Easy Demon", "Medium Demon", "Hard Demon", "Insane Demon", "Extreme Demon"];
        return order.indexOf(valueA) - order.indexOf(valueB);
      }
    },
    {
      field: "rating",
      flex: 1.7,
      minWidth: 100,
      filter: true,
      cellClassRules: {
        'featured': (p: any) => !this.enableRowStyle && p.data?.rating === 'Featured',
        'epic': (p: any) => !this.enableRowStyle && p.data?.rating === 'Epic',
        'legendary': (p: any) => !this.enableRowStyle && p.data?.rating === 'Legendary',
        'mythic': (p: any) => !this.enableRowStyle && p.data?.rating === 'Mythic'
      },
      comparator: (valueA: string, valueB: string) => {
        const order = ["Unrated", "Rated", "Featured", "Epic", "Legendary", "Mythic"];
        return order.indexOf(valueA) - order.indexOf(valueB);
      }
    },
    {
      field: "userCoins",
      headerName: "Coins",
      flex: 1.6,
      minWidth: 90,
      filter: true,
      cellStyle: { 'text-align': 'center' }
    },
    {
      field: "estimatedTime",
      headerName: "Est. Time",
      flex: 2,
      minWidth: 115,
      valueGetter: (params: any) => this.formatTime(Number(params.data?.estimatedTime || 0)),
      comparator: (valueA: any, valueB: any, nodeA: any, nodeB: any) => {
        return (Number(nodeA.data?.estimatedTime || 0)) - (Number(nodeB.data?.estimatedTime || 0));
      }
    },
    { field: "objects", flex: 1.5, minWidth: 90 },
    {
      field: "twop",
      flex: 0.85,
      minWidth: 60,
      headerName: "2p",
      cellStyle: {
        'text-align': 'center',
        'white-space': 'nowrap',
        'overflow': 'hidden',
        'text-overflow': 'clip'
      },
      cellRenderer: (params: any) => {
        return `<input type="checkbox" ${params.value ? 'checked' : ''} disabled />`;
      }
    },
    {
      field: "primarySong",
      flex: 3,
      minWidth: 170,
      filter: true,
      comparator: (valueA: string, valueB: string) => {
        const sanitizeString = (str: string) => str.replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
        const sanitizedA = sanitizeString(valueA);
        const sanitizedB = sanitizeString(valueB);
        return sanitizedA.localeCompare(sanitizedB);
      }
    },
    {
      field: "artist",
      flex: 2.3,
      minWidth: 140,
      filter: true,
      comparator: (valueA: string, valueB: string) => {
        const sanitizeString = (str: string) => str.replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
        const sanitizedA = sanitizeString(valueA);
        const sanitizedB = sanitizeString(valueB);
        return sanitizedA.localeCompare(sanitizedB);
      }
    },
    {
      field: "songID",
      flex: 1.8,
      minWidth: 100,
      valueFormatter: (params: any) => {
        return params.value;
      },
      comparator: (valueA: any, valueB: any) => {
        const isNumberA = !isNaN(valueA);
        const isNumberB = !isNaN(valueB);
        if (isNumberA && isNumberB) return valueA - valueB;
        else if (isNumberA) return -1;
        else if (isNumberB) return 1;
        return String(valueA).localeCompare(String(valueB));
      }
    },
    { field: "songs", flex: 1.2, minWidth: 75, cellStyle: { 'text-align': 'center' } },
    { field: "SFX", flex: 1, minWidth: 60, cellStyle: { 'text-align': 'center' } },
    {
      field: "rateDate",
      flex: 1.6,
      minWidth: 110,
      sortable: false,
      filter: true,
      comparator: (dateA: string, dateB: string) => {
        const parseDate = (dateStr: string) => {
          const [day, month, year] = dateStr.split('/').map(Number);
          return new Date(year, month - 1, day);
        };
        const parsedDateA = parseDate(dateA);
        const parsedDateB = parseDate(dateB);
        return parsedDateA.getTime() - parsedDateB.getTime();
      },
      valueFormatter: (params: any) => {
        return params.value;
      }
    }
  ];

  unratedColDefs: ColDef[] = this.colDefs.map(column => column.field === 'rateDate'
      ? { ...column, field: 'firstSeen', headerName: 'First Seen', sortable: false }
      : column);
}

/*
Copyright Google LLC. All Rights Reserved.
Use of this source code is governed by an MIT-style license that
can be found in the LICENSE file at https://angular.io/license
*/
