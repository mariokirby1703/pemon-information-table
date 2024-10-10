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
      songID: number | string;
      songs: number;
      SFX: number;
      rateDate: string;
    }[]>
    ('https://google.com', {withCredentials: true});
  }
}
