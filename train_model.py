from src.churn_model import train_all_models

column_mapping = {
    "고객ID": "고객ID",
    "주문번호": "주문번호",
    "거래일시": "거래일시",
    "매출": "매출",
    "단가": "단가",
    "수량": "수량",
    "카테고리": "카테고리",
    "상품명": "상품명",
}

if __name__ == "__main__":
    result = train_all_models(
        input_csv_path="pet2.csv",
        column_mapping=column_mapping,
        verbose=True,
    )
    print(result)