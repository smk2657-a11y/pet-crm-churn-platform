"""
mapping_ui.py에서 사용할 카테고리 병합 컴포넌트

위치: mapping_step() 함수의 render_quality_section() 호출 전에 추가
"""

import pandas as pd
import streamlit as st
from typing import Optional, Tuple, Dict


class CategoryMerger:
    """카테고리 정보가 없으면 제품 정보로 병합"""
    
    CATEGORY_KEYWORDS = ['category', '카테고리', 'cat_', '품목', '상품분류', '분류']
    PRODUCT_ID_KEYWORDS = ['product_id', '상품id', '상품ID', 'productid', 'product', '상품번호']
    
    @staticmethod
    def has_category(df: pd.DataFrame) -> bool:
        """데이터프레임에 카테고리 컬럼이 있는지 확인"""
        headers = [str(h).strip().lower() for h in df.columns]
        return any(kw in h for h in headers for kw in CategoryMerger.CATEGORY_KEYWORDS)
    
    @staticmethod
    def find_product_id_column(df: pd.DataFrame) -> Optional[str]:
        """상품ID 컬럼 찾기"""
        headers = [h.lower() for h in df.columns]
        for h, orig_h in zip(headers, df.columns):
            for kw in CategoryMerger.PRODUCT_ID_KEYWORDS:
                if kw.lower() in h:
                    return orig_h
        return None
    
    @staticmethod
    def find_category_column(df: pd.DataFrame) -> Optional[str]:
        """카테고리 컬럼 찾기"""
        headers = [h.lower() for h in df.columns]
        for h, orig_h in zip(headers, df.columns):
            for kw in CategoryMerger.CATEGORY_KEYWORDS:
                if kw.lower() in h:
                    return orig_h
        return None
    
    @staticmethod
    def merge(df_order: pd.DataFrame, df_product: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
        """주문 데이터와 제품 정보 병합"""
        try:
            # 카테고리 컬럼 찾기
            category_col = CategoryMerger.find_category_column(df_product)
            if not category_col:
                raise ValueError("제품 정보에서 카테고리 컬럼을 찾을 수 없습니다")
            
            # 상품ID 컬럼 찾기
            product_id_col = CategoryMerger.find_product_id_column(df_order)
            product_file_id_col = CategoryMerger.find_product_id_column(df_product)
            
            if not product_id_col:
                raise ValueError("주문 데이터에서 상품ID 컬럼을 찾을 수 없습니다")
            if not product_file_id_col:
                raise ValueError("제품 정보에서 상품ID 컬럼을 찾을 수 없습니다")
            
            # 제품 정보 맵핑
            product_map = {}
            for _, row in df_product.iterrows():
                pid = str(row[product_file_id_col]).strip()
                cat = str(row[category_col]).strip()
                if pid and cat and pid.lower() != 'nan':
                    product_map[pid] = cat
            
            # 주문 데이터에 카테고리 추가
            merged_df = df_order.copy()
            merged_df['카테고리'] = merged_df[product_id_col].astype(str).str.strip().map(
                lambda x: product_map.get(x, '분류_안됨')
            )
            
            # 통계
            matched = (merged_df['카테고리'] != '분류_안됨').sum()
            total = len(merged_df)
            match_rate = (matched / total * 100) if total > 0 else 0
            
            return merged_df, {
                'success': True,
                'total': total,
                'matched': matched,
                'match_rate': match_rate,
                'message': f'✅ {matched}건의 주문에 카테고리가 추가되었습니다 ({match_rate:.1f}%)'
            }
        except Exception as e:
            return None, {
                'success': False,
                'message': f'❌ 병합 실패: {str(e)}'
            }


def render_category_merge_section(df_std: pd.DataFrame) -> Optional[pd.DataFrame]:
    """
    카테고리 병합 UI 섹션
    
    mapping_step()의 "표준화 결과 미리보기" 이후에 호출
    
    Returns:
        병합된 데이터프레임 또는 None
    """
    
    # 1. 카테고리 정보 확인
    has_category = CategoryMerger.has_category(df_std)
    
    if has_category:
        st.markdown(
            """
            <div style="
                border:1px solid rgba(22,163,74,0.18);
                background:rgba(22,163,74,0.06);
                border-radius:16px;
                padding:16px 18px;
                color:#1f2937;
                margin-bottom:20px;
            ">
                ✅ <b>카테고리 정보 완료</b><br/>
                이미 카테고리 컬럼이 포함되어 있어서 추가 병합이 필요하지 않습니다.
            </div>
            """,
            unsafe_allow_html=True,
        )
        return None
    
    # 2. 카테고리 없음 - 병합 옵션 제시
    st.markdown(
        """
        <div style="
            border:1px solid rgba(239,68,68,0.20);
            background:rgba(239,68,68,0.07);
            border-radius:16px;
            padding:16px 18px;
            color:#1f2937;
            margin-bottom:20px;
        ">
            ⚠️ <b>카테고리 정보 누락</b><br/>
            현재 데이터에 카테고리 정보가 없습니다.<br/>
            제품 정보 파일(CSV/XLSX)을 추가로 업로드하면 자동으로 카테고리를 추가할 수 있습니다.
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    # 3. 제품 정보 파일 업로드
    st.markdown("#### 🔗 제품 정보 추가 업로드")
    st.caption("상품ID와 카테고리 컬럼이 포함된 파일을 업로드하세요")
    
    product_file = st.file_uploader(
        "CSV 또는 XLSX 파일",
        type=["csv", "xlsx"],
        key="product_file_for_merge",
        label_visibility="collapsed"
    )
    
    if product_file is None:
        st.info("📁 제품 정보 파일을 업로드하지 않으면 카테고리 없이 분석을 진행합니다")
        return None
    
    # 4. 제품 정보 로드
    try:
        if product_file.name.endswith('.csv'):
            df_product = pd.read_csv(product_file)
        else:
            df_product = pd.read_excel(product_file)
        st.success(f"✅ 제품 정보 로드됨 ({len(df_product):,}행)")
    except Exception as e:
        st.error(f"❌ 파일 읽기 실패: {e}")
        return None
    
    # 5. 병합 실행
    if st.button("🔗 카테고리 병합 실행", type="primary", use_container_width=True):
        merged_df, result = CategoryMerger.merge(df_std, df_product)
        
        if result['success']:
            st.markdown(
                f"""
                <div style="
                    border:1px solid rgba(22,163,74,0.18);
                    background:rgba(22,163,74,0.06);
                    border-radius:16px;
                    padding:16px 18px;
                    color:#1f2937;
                    margin:20px 0;
                ">
                    {result['message']}<br/>
                    <small>총 {result['total']:,}건 중 {result['matched']:,}건 매칭</small>
                </div>
                """,
                unsafe_allow_html=True,
            )
            
            # 프리뷰
            st.markdown("##### 📊 병합 결과 미리보기")
            st.dataframe(merged_df[['고객ID', '주문번호', '카테고리']].head(10), use_container_width=True)
            
            # 다운로드
            csv = merged_df.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                "📥 병합된 데이터 다운로드",
                data=csv,
                file_name="merged_with_category.csv",
                mime="text/csv",
                use_container_width=True
            )
            
            # 병합된 데이터 반환
            st.session_state['df_std'] = merged_df
            st.success("✅ 데이터가 업데이트되었습니다. 아래로 스크롤하여 계속 진행하세요.")
            return merged_df
        else:
            st.error(result['message'])
            return None
    
    return None
