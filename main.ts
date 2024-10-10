import { platformBrowserDynamic } from '@angular/platform-browser-dynamic';

import { AppModule } from './src/app/app.module';

/* Core Data Grid CSS */
import 'ag-grid-community/styles/ag-grid.css';
/* Quartz Theme Specific CSS */
import 'ag-grid-community/styles/ag-theme-quartz.css';

platformBrowserDynamic().bootstrapModule(AppModule)
  .catch(err => console.error(err));


/*
Copyright Google LLC. All Rights Reserved.
Use of this source code is governed by an MIT-style license that
can be found in the LICENSE file at https://angular.io/license
*/
