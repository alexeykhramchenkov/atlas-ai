-- Internal service-role writer. Reader/get_* contracts are unchanged.
CREATE OR REPLACE FUNCTION public.replace_stock_snapshot_rows(
    p_table text, p_user_id bigint, p_shop_id bigint, p_marketplace text,
    p_snapshot_date date, p_rows jsonb
) RETURNS integer
LANGUAGE plpgsql SECURITY INVOKER SET search_path = public, pg_temp AS $$
DECLARE
    cols text;
    selected_cols text;
    names text[];
    inserted integer := 0;
BEGIN
    IF p_table NOT IN ('normalized_stocks','snapshots_stocks_variants_daily',
        'snapshots_stocks_daily','metrics_stocks_variants_daily','metrics_stocks_daily')
       OR p_table IS NULL OR p_user_id IS NULL OR p_shop_id IS NULL
       OR p_marketplace IS NULL OR p_marketplace = ''
       OR p_rows IS NULL OR jsonb_typeof(p_rows) <> 'array' THEN
        RAISE EXCEPTION 'Invalid stock replacement scope';
    END IF;
    IF (p_table = 'normalized_stocks') <> (p_snapshot_date IS NULL) THEN
        RAISE EXCEPTION 'Invalid stock snapshot date';
    END IF;
    -- Serialize same-tenant inventory writes, including concurrent scheduled repairs.
    PERFORM pg_advisory_xact_lock(hashtextextended(
        p_user_id::text || ':' || p_shop_id::text || ':' || p_marketplace || ':stocks', 0));
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(p_rows) r WHERE
        jsonb_typeof(r) <> 'object'
        OR (r->>'user_id') IS DISTINCT FROM p_user_id::text
        OR (r->>'shop_id') IS DISTINCT FROM p_shop_id::text
        OR (r->>'marketplace') IS DISTINCT FROM p_marketplace
        OR (p_snapshot_date IS NOT NULL AND (r->>'snapshot_date') IS DISTINCT FROM p_snapshot_date::text)) THEN
        RAISE EXCEPTION 'Stock row outside replacement scope';
    END IF;
    IF jsonb_array_length(p_rows) > 0 THEN
        SELECT array_agg(k ORDER BY k) INTO names FROM jsonb_object_keys(p_rows->0) k;
        IF EXISTS (SELECT 1 FROM jsonb_array_elements(p_rows) r WHERE
            ARRAY(SELECT k FROM jsonb_object_keys(r) k ORDER BY k) <> names) THEN
            RAISE EXCEPTION 'Stock rows have inconsistent columns';
        END IF;
        IF EXISTS (SELECT 1 FROM unnest(names) n WHERE n = 'id' OR NOT EXISTS (
            SELECT 1 FROM information_schema.columns c WHERE c.table_schema='public'
                AND c.table_name=p_table AND c.column_name=n AND c.is_generated='NEVER')) THEN
            RAISE EXCEPTION 'Invalid stock replacement column';
        END IF;
        SELECT string_agg(format('%I', n), ','), string_agg(format('r.%I', n), ',')
            INTO cols, selected_cols FROM unnest(names) n;
    END IF;
    IF p_snapshot_date IS NULL THEN
        EXECUTE format('DELETE FROM public.%I WHERE user_id=$1 AND shop_id=$2 AND marketplace=$3',p_table)
            USING p_user_id,p_shop_id,p_marketplace;
    ELSE
        EXECUTE format('DELETE FROM public.%I WHERE user_id=$1 AND shop_id=$2 AND marketplace=$3 AND snapshot_date=$4',p_table)
            USING p_user_id,p_shop_id,p_marketplace,p_snapshot_date;
    END IF;
    IF cols IS NOT NULL THEN
        EXECUTE format('INSERT INTO public.%I (%s) SELECT %s FROM jsonb_populate_recordset(NULL::public.%I,$1) r',
            p_table,cols,selected_cols,p_table) USING p_rows;
        GET DIAGNOSTICS inserted = ROW_COUNT;
    END IF;
    RETURN inserted;
END $$;
REVOKE ALL ON FUNCTION public.replace_stock_snapshot_rows(text,bigint,bigint,text,date,jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.replace_stock_snapshot_rows(text,bigint,bigint,text,date,jsonb) TO service_role;
NOTIFY pgrst, 'reload schema';
