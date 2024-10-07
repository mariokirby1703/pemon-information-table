import { Component, OnInit } from '@angular/core';
import { AgGridAngular } from 'ag-grid-angular'; // Angular Data Grid Component
import { ColDef } from 'ag-grid-community'; // Column Definition Type Interface
import { CartService } from './cart.service';
import { CookieService } from 'ngx-cookie-service';
import { HttpClient } from '@angular/common/http';

@Component({
  selector: 'app-root',
  //standalone: false,
  //imports: [AgGridAngular], // Add Angular Data Grid Component
  styleUrls: ['./app.component.css'],
  templateUrl: `./app.component.html`
})

export class AppComponent implements OnInit {
  private cookie_name='';
  private all_cookies : any ='';

  public pagination = true;
  public paginationPageSize = 301;
  public paginationPageSizeSelector: number[] | boolean = [10, 25, 50, 100, 150, 301, 500, 1000];

  constructor(private cartService: CartService, private cookieService: CookieService, private http: HttpClient) { }

  setCookie(){
    this.cookieService.set('name','Tutorialswebsite');
  }

  deleteCookie(){
    this.cookieService.delete('name');
  }

  deleteAll(){
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
    songID: number;
    songs: number;
    SFX: number;
    rateDate: string;
  }[];

  rawData: any[] = [];

  ngOnInit(): void {
    this.cookie_name=this.cookieService.get('PHPSESSID');
    this.all_cookies=this.cookieService.getAll();
    this.cartService.getRowData().subscribe(value => this.rowData = value);

    this.http.get<any[]>('assets/pemons.json').subscribe(
        data => {
          this.rawData = data;
          console.log('JSON data loaded:', this.rawData); // For debugging
        },
        error => {
          console.error('Error loading JSON file:', error);
        }
    );
  }

  // Utility function to convert seconds to dynamic time format (H:M:S)
  formatTime(seconds: number): string {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;

    // Only show hours if it's non-zero, otherwise show only minutes and seconds
    if (hours > 0) {
      return `${hours}h ${minutes}m ${secs}s`;
    } else if (minutes > 0) {
      return `${minutes}m ${secs}s`;
    } else {
      return `${secs}s`;
    }
  }

  /* rowClassRules = {
    'easy': (p:any) => p.data.difficulty == "Easy Demon",
    'medium': (p:any) => p.data.difficulty == "Medium Demon",
    'hard': (p:any) => p.data.difficulty == "Hard Demon",
    'insane': (p:any) => p.data.difficulty == "Insane Demon",
    'extreme': (p:any) => p.data.difficulty == "Extreme Demon"
  } */

  // Column Definitions: Defines the columns to be displayed.
  colDefs: ColDef[] = [
    { field: "number", flex: 1.4, cellStyle: { 'text-align': 'center' } },
    {
      field: "level",
      flex: 3.2,
      filter: true,
      comparator: (valueA: string, valueB: string) => {
        return valueA.toLowerCase().localeCompare(valueB.toLowerCase());
      }
    },
    {
      field: "creator",
      flex: 2.6,
      filter: true,
      comparator: (valueA: string, valueB: string) => {
        return valueA.toLowerCase().localeCompare(valueB.toLowerCase());
      }
    },
    { field: "ID", flex: 1.8, headerName: "Level ID" },
    {
      field: "difficulty",
      flex: 2.4,
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

        // Get the index of each difficulty in the custom order array
        const indexA = order.indexOf(valueA);
        const indexB = order.indexOf(valueB);

        // Sort based on the index in the custom order array
        return indexA - indexB;
      }
    },
    {
      field: "rating",
      flex: 1.7,
      filter: true,
      cellClassRules: {
        'featured': (p:any) => p.data.rating == "Featured",
        'epic': (p:any) => p.data.rating == "Epic",
        'legendary': (p:any) => p.data.rating == "Legendary",
        'mythic': (p:any) => p.data.rating == "Mythic"
      },
      comparator: (valueA: string, valueB: string) => {
        const order = ["Rated", "Featured", "Epic", "Legendary", "Mythic"];

        // Get the index of each rating in the custom order array
        const indexA = order.indexOf(valueA);
        const indexB = order.indexOf(valueB);

        // Sort based on the index in the custom order array
        return indexA - indexB;
      }
    },
    {
      field: "userCoins",
      headerName: "Coins",
      flex: 1.6,
      filter: true,
      cellStyle: { 'text-align': 'center' }
    },
    {
      field: "estimatedTime",
      headerName: "Est. Time",
      flex: 2,
      valueGetter: (params: any) => this.formatTime(params.data.estimatedTime),
      comparator: (valueA: any, valueB: any, nodeA: any, nodeB: any) => {
        // Sort based on the raw seconds value, not the formatted time
        return nodeA.data.estimatedTime - nodeB.data.estimatedTime;
      }
    },
    { field: "objects", flex: 1.5 },
    { field: "checkpoints", flex: 1.9, cellStyle: { 'text-align': 'center' } },
    {
      field: "twop",
      flex: 0.85,
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
      filter: true,
      comparator: (valueA: string, valueB: string) => {
        // Function to remove all non-alphanumeric characters from the string
        const sanitizeString = (str: string) => str.replace(/[^a-zA-Z0-9]/g, '').toLowerCase();

        // Sanitize both values to remove special characters
        const sanitizedA = sanitizeString(valueA);
        const sanitizedB = sanitizeString(valueB);

        // Compare the sanitized values
        return sanitizedA.localeCompare(sanitizedB);
      }
    },
    {
      field: "artist",
      flex: 2.5,
      filter: true,
      comparator: (valueA: string, valueB: string) => {
        // Function to remove all non-alphanumeric characters from the string
        const sanitizeString = (str: string) => str.replace(/[^a-zA-Z0-9]/g, '').toLowerCase();

        // Sanitize both values to remove special characters
        const sanitizedA = sanitizeString(valueA);
        const sanitizedB = sanitizeString(valueB);

        // Compare the sanitized values
        return sanitizedA.localeCompare(sanitizedB);
      }
    },
    { field: "songID", flex: 1.8 },
    { field: "songs", flex: 1.3, cellStyle: { 'text-align': 'center' } },
    { field: "SFX", flex: 1, cellStyle: { 'text-align': 'center' } },
    { 
      field: "rateDate", 
      flex: 1.6,
      sortable: false,
      comparator: (dateA: string, dateB: string) => {
        const parseDate = (dateStr: string) => {
          const [day, month, year] = dateStr.split('/').map(Number);
          return new Date(year, month - 1, day); // Parse DD/MM/YYYY
        };
  
        const parsedDateA = parseDate(dateA);
        const parsedDateB = parseDate(dateB);
  
        return parsedDateA.getTime() - parsedDateB.getTime();
      },
      valueFormatter: (params: any) => {
        // Ensure the date remains displayed in DD/MM/YYYY format
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
