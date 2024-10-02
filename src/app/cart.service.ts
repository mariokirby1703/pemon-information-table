import { HttpClient } from '@angular/common/http';
import { Product } from './products';
import { Injectable } from '@angular/core';

@Injectable({
  providedIn: 'root'
})
export class CartService {
  items: Product[] = [];

  constructor(
    private http: HttpClient
  ) {}

  addToCart(product: Product) {
    this.items.push(product);
  }

  getItems() {
    return this.items;
  }

  clearCart() {
    this.items = [];
    return this.items;
  }

  /*
  getData() {
    return this.http.get<{ Id: number, SystemId: number, Vorname: string, Nachname: string, SimpleRole: string, IsFavorit: boolean, IsActive: boolean, PinCode: string, ColorCode: string, Date: string, State: string }[]>
    ('https://webbackend.volkmann-rossbach.de/api/mitarbeiter')
        .subscribe(data => {
          console.log(JSON.stringify(data));
        }
  )};
  */

  getRowData() {
    return this.http.get<{
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
    }[]>
    ('https://webbackend.volkmann-rossbach.de/api/mitarbeiter', {withCredentials: true});
  }
}
