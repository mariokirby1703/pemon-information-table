import { Component, OnInit } from '@angular/core';
import { AgGridAngular } from 'ag-grid-angular'; // Angular Data Grid Component
import { ColDef } from 'ag-grid-community'; // Column Definition Type Interface
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

  public gridOptions = {
    animateRows: true
  };

  public pagination = true;
  public paginationPageSize = 500;
  public paginationPageSizeSelector: number[] | boolean = [10, 25, 50, 100, 150, 250, 500];

  constructor(private cartService: CartService, private cookieService: CookieService, private http: HttpClient) { }

  setCookie() {
    this.cookieService.set('name', 'Tutorialswebsite');
  }

  deleteCookie() {
    this.cookieService.delete('name');
  }

  deleteAll() {
    this.cookieService.deleteAll();
  }

  rowData!: {
    number: number;
    level: string;
    creator: string;
    ID: number;
    difficulty: string;
    rating: string;
    userCoins: number;
    estimatedTime: number;
    objects: number;
    checkpoints: number;
    twop: boolean;
    primarySong: string;
    artist: string;
    songID: number | string;
    songs: number;
    SFX: number;
    rateDate: string;
  }[];

  rawData: any[] = [];

  ngOnInit(): void {
    this.cookie_name = this.cookieService.get('PHPSESSID');
    this.all_cookies = this.cookieService.getAll();
  
    this.http.get<any[]>('assets/pemons.json').subscribe(
      data => {
        this.rawData = data;
        console.log('JSON data loaded:', this.rawData); // For debugging
        this.rowData = this.rawData; // Set rowData after loading
        this.updateCustomPaginationText(); // Update text after data load
      },
      error => {
        console.error('Error loading JSON file:', error);
      }
    );
  }

  updateCustomPaginationText(): void {
    setTimeout(() => {
      const paginationPanel = document.querySelector('.ag-paging-panel');
      if (paginationPanel) {
        // Check if custom text already exists
        let customPaginationText = document.getElementById('customPaginationText');
        if (!customPaginationText) {
          customPaginationText = document.createElement('span');
          customPaginationText.id = 'customPaginationText';
          customPaginationText.innerText = '© Developed by mariokirby1703 - Information gathered by mariokirby1703 and Lutz127'; // Static text
          paginationPanel.insertBefore(customPaginationText, paginationPanel.firstChild); // Add the text to the left
        }
      }
    }, 0); // Ensures this runs after the current call stack clears
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
    }
    ,
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
        'easy': (p:any) => p.data.difficulty == "Easy Demon",
        'medium': (p:any) => p.data.difficulty == "Medium Demon",
        'hard': (p:any) => p.data.difficulty == "Hard Demon",
        'insane': (p:any) => p.data.difficulty == "Insane Demon",
        'extreme': (p:any) => p.data.difficulty == "Extreme Demon"
      },
      comparator: (valueA: string, valueB: string) => {
        const order = ["Easy Demon", "Medium Demon", "Hard Demon", "Insane Demon", "Extreme Demon"];
        const indexA = order.indexOf(valueA);
        const indexB = order.indexOf(valueB);
        return indexA - indexB;
      }
    },
    {
      field: "rating",
      flex: 1.7,
      minWidth: 100,  // Prevents rating from being too small
      filter: true,
      cellClassRules: {
        'featured': (p:any) => p.data.rating == "Featured",
        'epic': (p:any) => p.data.rating == "Epic",
        'legendary': (p:any) => p.data.rating == "Legendary",
        'mythic': (p:any) => p.data.rating == "Mythic"
      },
      comparator: (valueA: string, valueB: string) => {
        const order = ["Rated", "Featured", "Epic", "Legendary", "Mythic"];
        const indexA = order.indexOf(valueA);
        const indexB = order.indexOf(valueB);
        return indexA - indexB;
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
    { field: "objects", flex: 1.5, minWidth: 90 }, // Avoids objects column from collapsing
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
