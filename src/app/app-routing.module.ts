import { Component, NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { DemonsGridComponent } from './demons-grid/demons-grid.component';

// The root component owns the platformer grid on both platformer URLs.
@Component({ standalone: true, template: '' })
export class UnratedRouteComponent {}

const routes: Routes = [
    { path: 'unrated-pemons', component: UnratedRouteComponent },
    { path: 'demons', component: DemonsGridComponent },
    // alles andere bleibt deine AppComponent (kein Route-Target nötig)
    { path: '**', redirectTo: '' }
];

@NgModule({
    imports: [RouterModule.forRoot(routes, { scrollPositionRestoration: 'enabled' })],
    exports: [RouterModule]
})
export class AppRoutingModule {}
