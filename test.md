# System requirement specifications
## Functional Request Specifications
1. Install system
2. gila
3. bola

| Name  | Age |  City    |
|-------|-----|-------|
| Alice | 25  | New York |
| Bob   | 30  | London   |


```mermaid
erDiagram
  User ||--o{ Order : "places"
  Order ||--|| Item : "contains"
  User {
    int id PK
    string name
  }
  Order {
    int order_id PK
  }
 Item {
    int item_id PK
}  
```