import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { AgGridAngular } from 'ag-grid-angular';
import { ColDef, RowStyle, RowClassParams } from 'ag-grid-community';
import { CartService } from './cart.service';
import { CookieService } from 'ngx-cookie-service';
import { HttpClient } from '@angular/common/http';

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

  constructor(private cartService: CartService, private cookieService: CookieService, private http: HttpClient, private cdr: ChangeDetectorRef) {}

  rowData!: any[];
  rawData: any[] = [];

  getRowStyle = (params: RowClassParams<any, any>): RowStyle | undefined => {
    if (this.enableRowStyle && params.data && params.data.ID) {
      return {
        backgroundImage: `url("https://raw.githubusercontent.com/cdc-sys/level-thumbnails/main/thumbs/${params.data.ID}.png")`,
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

  ngOnInit(): void {
    this.gridOptions = {
      animateRows: true,
      getRowStyle: this.getRowStyle
    };

    this.cookie_name = this.cookieService.get('PHPSESSID');
    this.all_cookies = this.cookieService.getAll();

    this.http.get<any[]>('assets/pemons.json').subscribe(
        data => {
          this.rawData = data;
          this.rowData = [...this.rawData]; // Set initial rowData without sorting
          this.updateCustomPaginationText();
          this.cdr.detectChanges();
        },
        error => {
          console.error('Error loading JSON file:', error);
        }
    );
  }

  toggleRowStyle(): void {
    this.enableRowStyle = !this.enableRowStyle;
    this.updateColumnStyles();
    if (this.gridOptions.api) {
      this.gridOptions.api.refreshCells({ force: true, columns: ['difficulty', 'rating'] });
      this.gridOptions.api.redrawRows();
    }
    console.log('Row style toggled:', this.enableRowStyle);
    this.colDefs = this.colDefs.map(col => {
      if (col.field === 'difficulty' || col.field === 'rating') {
        return {
          ...col,
          cellClassRules: this.enableRowStyle ? {} : {
            'easy': (p: any) => p.data.difficulty === 'Easy Demon',
            'medium': (p: any) => p.data.difficulty === 'Medium Demon',
            'hard': (p: any) => p.data.difficulty === 'Hard Demon',
            'insane': (p: any) => p.data.difficulty === 'Insane Demon',
            'extreme': (p: any) => p.data.difficulty === 'Extreme Demon',
            'featured': (p: any) => p.data.rating === 'Featured',
            'epic': (p: any) => p.data.rating === 'Epic',
            'legendary': (p: any) => p.data.rating === 'Legendary',
            'mythic': (p: any) => p.data.rating === 'Mythic'
          }
        };
      }
      return col;
    });
    if (this.gridOptions.api) {
      this.gridOptions.api.setColumnDefs([...this.colDefs]);
      this.gridOptions.api.refreshCells({ force: true, columns: ['difficulty', 'rating'] });
      this.gridOptions.api.redrawRows();
    }
    console.log('Row style toggled:', this.enableRowStyle);
    console.log(this.enableRowStyle ? 'Cell styles will be removed.' : 'Cell styles will be applied.');
    this.updateColumnStyles();
    if (this.gridOptions.api) {
      this.gridOptions.api.redrawRows();
    }
    this.rowData = [...this.rowData];
    setTimeout(() => {
      this.cdr.detectChanges();
    }, 0);
  }

  updateColumnStyles(): void {
    this.colDefs.forEach((col) => {
      if (this.enableRowStyle) {
        console.log('Removing cell styles for:', col.field);
        col.cellClassRules = {};
      } else {
        console.log('Applying cell styles for:', col.field);
        
        if (col.field === 'difficulty') {
          col.cellClassRules = {
            'easy': (p: any) => p.data.difficulty === 'Easy Demon',
            'medium': (p: any) => p.data.difficulty === 'Medium Demon',
            'hard': (p: any) => p.data.difficulty === 'Hard Demon',
            'insane': (p: any) => p.data.difficulty === 'Insane Demon',
            'extreme': (p: any) => p.data.difficulty === 'Extreme Demon',
          };
        } else if (col.field === 'rating') {
          col.cellClassRules  = {
            'featured': (p: any) => p.data.rating === 'Featured',
            'epic': (p: any) => p.data.rating === 'Epic',
            'legendary': (p: any) => p.data.rating === 'Legendary',
            'mythic': (p: any) => p.data.rating === 'Mythic'
          };
        }
      }
    });
    if (this.gridOptions.api) {
      this.gridOptions.api.setColumnDefs([...this.colDefs]);
      this.gridOptions.api.refreshCells({ force: true, columns: ['difficulty', 'rating'] });
      this.gridOptions.api.redrawRows();
    }
    if (this.gridOptions.api) {
      this.gridOptions.api.setColumnDefs([...this.colDefs]);
      this.gridOptions.api.refreshCells({ force: true, columns: ['difficulty', 'rating'] });
    }
  }

  updateCustomPaginationText(): void {
    setTimeout(() => {
      const paginationPanel = document.querySelector('.ag-paging-panel');
      if (paginationPanel) {
        let customPaginationText = document.getElementById('customPaginationText');
        if (!customPaginationText) {
          customPaginationText = document.createElement('span');
          customPaginationText.id = 'customPaginationText';
          customPaginationText.innerText = '© Developed by mariokirby1703 - Information gathered by mariokirby1703 and Lutz127';
          paginationPanel.insertBefore(customPaginationText, paginationPanel.firstChild);
        }

        let toggleContainer = document.getElementById('toggleContainer');
        if (!toggleContainer) {
          toggleContainer = document.createElement('div');
          toggleContainer.id = 'toggleContainer';
          toggleContainer.className = 'switch-container';

          toggleContainer.innerHTML = `
            <label class="switch">
              <input type="checkbox" id="rowStyleToggle" checked>
              <span class="slider round"></span>
            </label>
            <span class="switch-label">Row Style</span>
          `;

          paginationPanel.appendChild(toggleContainer);

          document.getElementById('rowStyleToggle')?.addEventListener('change', (event) => {
            const inputElement = event.target as HTMLInputElement;
            this.enableRowStyle = inputElement.checked;
            this.toggleRowStyle();
          });
        }
      }
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
      },
      cellRenderer: (params: any) => {
        if (params.data && params.data.showcase) {
          const link = document.createElement('a');
          link.href = params.data.showcase;
          link.target = '_blank'; // Open in a new tab
          link.rel = 'noopener noreferrer'; // Prevent security issues
          link.innerText = params.value;
          link.style.textDecoration = 'none'; // Optional: underline the link
          return link;
        }
        return params.value; // Fallback in case showcase is missing
      }
    },
    {
      field: "creator",
      flex: 2.5,
      minWidth: 150,  // Ensures creator name stays readable
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
        'easy': (p: any) => p.data.difficulty === 'Easy Demon',
        'medium': (p: any) => p.data.difficulty === 'Medium Demon',
        'hard': (p: any) => p.data.difficulty === 'Hard Demon',
        'insane': (p: any) => p.data.difficulty === 'Insane Demon',
        'extreme': (p: any) => p.data.difficulty === 'Extreme Demon',
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
        'featured': (p: any) => p.data.rating === 'Featured',
        'epic': (p: any) => p.data.rating === 'Epic',
        'legendary': (p: any) => p.data.rating === 'Legendary',
        'mythic': (p: any) => p.data.rating === 'Mythic'
      },
      comparator: (valueA: string, valueB: string) => {
        const order = ["Rated", "Featured", "Epic", "Legendary", "Mythic"];
        return order.indexOf(valueA) - order.indexOf(valueB);
      }
    },
    {
      field: "userCoins",
      headerName: "Coins",
      flex: 1.6,
      minWidth: 90,  // Keeps the Coins column wide enough to be legible
      filter: true,
      cellStyle: { 'text-align': 'center' }
    },
    {
      field: "estimatedTime",
      headerName: "Est. Time",
      flex: 2,
      minWidth: 115,
      valueGetter: (params: any) => this.formatTime(params.data.estimatedTime),
      comparator: (valueA: any, valueB: any, nodeA: any, nodeB: any) => {
        return nodeA.data.estimatedTime - nodeB.data.estimatedTime;
      }
    },
    { field: "objects", flex: 1.5, minWidth: 90 },
    { field: "checkpoints", flex: 1.9, minWidth: 110, cellStyle: { 'text-align': 'center' } },
    {
      field: "twop",
      flex: 0.85,
      minWidth: 60,  // Ensure checkbox column is not too narrow
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
      minWidth: 170,  // Ensures song name is readable
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
      minWidth: 140,  // Ensures artist name stays visible
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
      minWidth: 100,  // Ensures song ID remains visible
      valueFormatter: (params: any) => {
        return params.value;
      },
      comparator: (valueA: any, valueB: any) => {
        const isNumberA = !isNaN(valueA);
        const isNumberB = !isNaN(valueB);
        if (isNumberA && isNumberB) return valueA - valueB;
        else if (isNumberA) return -1;
        else if (isNumberB) return 1;
        return valueA.localeCompare(valueB);
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


}


/*
Copyright Google LLC. All Rights Reserved.
Use of this source code is governed by an MIT-style license that
can be found in the LICENSE file at https://angular.io/license
*/
