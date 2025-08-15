import { ComponentFixture, TestBed } from '@angular/core/testing';

import { DemonsGridComponent } from './demons-grid.component';

describe('DemonsGridComponent', () => {
  let component: DemonsGridComponent;
  let fixture: ComponentFixture<DemonsGridComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [DemonsGridComponent]
    })
    .compileComponents();
    
    fixture = TestBed.createComponent(DemonsGridComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
