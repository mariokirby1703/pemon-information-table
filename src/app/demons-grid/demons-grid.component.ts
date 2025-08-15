import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import {
  GridApi,
  GridReadyEvent,
  ColDef,
  RowStyle,
  RowClassParams
} from 'ag-grid-community';

@Component({
  selector: 'app-demons-grid',
  styleUrls: ['./demons-grid.component.css'],
  templateUrl: './demons-grid.component.html'
})
export class DemonsGridComponent implements OnInit {
  public gridOptions: any = { animateRows: true }; // keep if you want
  public pagination = true;
  public paginationPageSize = 100;
  public paginationPageSizeSelector: number[] | boolean = [10, 25, 50, 100, 150, 250, 500, 1000];

  public enableRowStyle = false; // default OFF
  private gridApi?: GridApi;

  rowData!: any[];
  rawData: any[] = [];

  constructor(
      private http: HttpClient,
      private cdr: ChangeDetectorRef,
      private router: Router
  ) {}

  private applyColDefsUpdate(): void {
    if (!this.gridApi) return;
    const api: any = this.gridApi;

    if (typeof api.setColumnDefs === 'function') {
      // ältere AG Grid Versionen
      api.setColumnDefs([...this.colDefs]);
    } else if (typeof api.setGridOption === 'function') {
      // neuere AG Grid Versionen (v31+)
      api.setGridOption('columnDefs', [...this.colDefs]);
    } else {
      // Fallback: Header & Zellen refreshen
      this.gridApi.refreshHeader();
      this.gridApi.refreshCells({ force: true, columns: ['difficulty', 'rating'] });
    }
  }

  ngOnInit(): void {
    this.http.get<any[]>('assets/demons.json').subscribe({
      next: (data) => {
        this.rawData = data;
        this.rowData = [...this.rawData];
        this.cdr.detectChanges();
      },
      error: (err) => console.error('Error loading demons.json:', err)
    });
  }

  onGridReady(event: GridReadyEvent): void {
    this.gridApi = event.api;                 // API merken
    this.updateCustomPaginationText();        // Footer-Switches aufbauen
    // Toggle-Status synchronisieren, falls DOM schon existiert
    const rowStyleToggle = document.getElementById('rowStyleToggle') as HTMLInputElement | null;
    if (rowStyleToggle) {
      rowStyleToggle.checked = this.enableRowStyle;
      rowStyleToggle.disabled = !this.gridApi;
    }
  }

  // Row-Background für Thumbnails
  getRowStyle = (params: RowClassParams<any, any>): RowStyle | undefined => {
    if (this.enableRowStyle && params.data && params.data.ID) {
      return {
        backgroundImage: `url("https://levelthumbs.prevter.me/thumbnail/${params.data.ID}")`,
        backgroundSize: 'cover',
        backgroundRepeat: 'no-repeat',
        backgroundPosition: 'center',
        backgroundColor: 'rgba(0,0,0,0.3)',
        backgroundBlendMode: 'darken',
        borderBottom: '2px solid #000'
      };
    }
    return undefined;
  };

  // <-- einzig wahre Schaltfunktion (kein Doppel-Flip)
  setRowStyle(enabled: boolean): void {
    if (this.enableRowStyle === enabled) return;
    this.enableRowStyle = enabled;

    this.updateColumnStyles();
    this.applyColDefsUpdate(); // <<— HIER statt setColumnDefs
    this.gridApi?.redrawRows();
  }

  updateColumnStyles(): void {
    this.colDefs.forEach((col) => {
      if (this.enableRowStyle) {
        col.cellClassRules = {};
      } else {
        if (col.field === 'difficulty') {
          col.cellClassRules = {
            easy:   (p: any) => p.data.difficulty === 'Easy Demon',
            medium: (p: any) => p.data.difficulty === 'Medium Demon',
            hard:   (p: any) => p.data.difficulty === 'Hard Demon',
            insane: (p: any) => p.data.difficulty === 'Insane Demon',
            extreme:(p: any) => p.data.difficulty === 'Extreme Demon',
          };
        } else if (col.field === 'rating') {
          col.cellClassRules = {
            featured:  (p: any) => p.data.rating === 'Featured',
            epic:      (p: any) => p.data.rating === 'Epic',
            legendary: (p: any) => p.data.rating === 'Legendary',
            mythic:    (p: any) => p.data.rating === 'Mythic',
          };
        }
      }
    });
  }

  updateCustomPaginationText(): void {
    setTimeout(() => {
      const paginationPanel = document.querySelector('.ag-paging-panel') as HTMLElement | null;
      if (!paginationPanel) return;

      // © Text
      let customPaginationText = document.getElementById('customPaginationText') as HTMLSpanElement | null;
      if (!customPaginationText) {
        customPaginationText = document.createElement('span');
        customPaginationText.id = 'customPaginationText';
        customPaginationText.innerText =
            '© Developed by mariokirby1703 - Information gathered by mariokirby1703 and Lutz127';
        paginationPanel.insertBefore(customPaginationText, paginationPanel.firstChild);
      }

      // Row Style Toggle
      let rowStyleToggle = document.getElementById('rowStyleToggle') as HTMLInputElement | null;
      if (!rowStyleToggle) {
        const toggleContainer = document.createElement('div');
        toggleContainer.id = 'toggleContainer';
        toggleContainer.className = 'switch-container';
        toggleContainer.innerHTML = `
          <label class="switch">
            <input type="checkbox" id="rowStyleToggle">
            <span class="slider round"></span>
          </label>
          <span class="switch-label">Row Style</span>
        `;
        paginationPanel.appendChild(toggleContainer);
        rowStyleToggle = document.getElementById('rowStyleToggle') as HTMLInputElement | null;
      }
      if (rowStyleToggle) {
        rowStyleToggle.checked = this.enableRowStyle;
        rowStyleToggle.disabled = !this.gridApi;
        rowStyleToggle.onchange = (ev: Event) => {
          const input = ev.target as HTMLInputElement;
          this.setRowStyle(input.checked);
        };
      }

      // Dataset-Switch (wir sind auf /demons → checked = true)
      let datasetToggle = document.getElementById('datasetToggle') as HTMLInputElement | null;
      if (!datasetToggle) {
        const datasetSwitch = document.createElement('div');
        datasetSwitch.id = 'datasetSwitch';
        datasetSwitch.className = 'switch-container';
        datasetSwitch.style.marginLeft = '12px';
        datasetSwitch.innerHTML = `
          <label class="switch">
            <input type="checkbox" id="datasetToggle">
            <span class="slider round"></span>
          </label>
            <span class="switch-label">Demons</span>
        `;
        paginationPanel.appendChild(datasetSwitch);
        datasetToggle = document.getElementById('datasetToggle') as HTMLInputElement | null;
      }
      if (datasetToggle) {
        datasetToggle.checked = true;
        datasetToggle.onchange = (ev: Event) => {
          const input = ev.target as HTMLInputElement;
          if (!input.checked) this.router.navigateByUrl('');
        };
      }
    }, 0);
  }

  // Spalten
  colDefs: ColDef[] = [
    { field: 'number', flex: 1.4, minWidth: 85, cellStyle: { 'text-align': 'center' } },
    {
      field: 'level',
      headerName: 'Level Name',
      flex: 3.3, minWidth: 190, filter: true,
      comparator: (a: string, b: string) => a.toLowerCase().localeCompare(b.toLowerCase()),
      cellRenderer: (p: any) => p.value
    },
    {
      field: 'creator',
      flex: 2.5, minWidth: 150, filter: true,
      comparator: (a: string, b: string) => a.toLowerCase().localeCompare(b.toLowerCase())
    },
    { field: 'ID', headerName: 'Level ID', flex: 1.8, minWidth: 110 },
    {
      field: 'difficulty',
      flex: 2.4, minWidth: 140, filter: true,
      cellClassRules: {
        'easy':   (p: any) => p.data.difficulty === 'Easy Demon',
        'medium': (p: any) => p.data.difficulty === 'Medium Demon',
        'hard':   (p: any) => p.data.difficulty === 'Hard Demon',
        'insane': (p: any) => p.data.difficulty === 'Insane Demon',
        'extreme':(p: any) => p.data.difficulty === 'Extreme Demon',
      },
      comparator: (a: string, b: string) => {
        const order = ['Easy Demon', 'Medium Demon', 'Hard Demon', 'Insane Demon', 'Extreme Demon'];
        return order.indexOf(a) - order.indexOf(b);
      }
    },
    {
      field: 'rating',
      flex: 1.7, minWidth: 100, filter: true,
      cellClassRules: {
        'featured':  (p: any) => p.data.rating === 'Featured',
        'epic':      (p: any) => p.data.rating === 'Epic',
        'legendary': (p: any) => p.data.rating === 'Legendary',
        'mythic':    (p: any) => p.data.rating === 'Mythic'
      },
      comparator: (a: string, b: string) => {
        const order = ['Rated', 'Featured', 'Epic', 'Legendary', 'Mythic'];
        return order.indexOf(a) - order.indexOf(b);
      }
    },
    { field: 'userCoins', headerName: 'Coins', flex: 1.6, minWidth: 90, filter: true, cellStyle: { 'text-align': 'center' } },
    { field: 'length', flex: 1.6, minWidth: 100, filter: true },
    { field: 'objects', flex: 1.5, minWidth: 90 },
    {
      field: 'twop',
      headerName: '2p',
      flex: 0.85, minWidth: 60,
      cellStyle: { 'text-align': 'center', 'white-space': 'nowrap', 'overflow': 'hidden', 'text-overflow': 'clip' },
      cellRenderer: (p: any) => `<input type="checkbox" ${p.value ? 'checked' : ''} disabled />`
    },
    {
      field: 'primarySong',
      flex: 3, minWidth: 170, filter: true,
      comparator: (a: string, b: string) => {
        const s = (x: string) => x.replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
        return s(a).localeCompare(s(b));
      }
    },
    {
      field: 'artist',
      flex: 2.3, minWidth: 140, filter: true,
      comparator: (a: string, b: string) => {
        const s = (x: string) => x.replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
        return s(a).localeCompare(s(b));
      }
    },
    {
      field: 'songID',
      flex: 1.8, minWidth: 100,
      valueFormatter: (p: any) => p.value,
      comparator: (a: any, b: any) => {
        const na = !isNaN(a), nb = !isNaN(b);
        if (na && nb) return a - b;
        if (na) return -1;
        if (nb) return 1;
        return String(a).localeCompare(String(b));
      }
    }
  ];
}
