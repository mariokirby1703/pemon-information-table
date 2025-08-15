import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { DemonsGridComponent } from './demons-grid/demons-grid.component';

const routes: Routes = [
    { path: 'demons', component: DemonsGridComponent },
    // alles andere bleibt deine AppComponent (kein Route-Target nötig)
    { path: '**', redirectTo: '' }
];

@NgModule({
    imports: [RouterModule.forRoot(routes, { scrollPositionRestoration: 'enabled' })],
    exports: [RouterModule]
})
export class AppRoutingModule {}
