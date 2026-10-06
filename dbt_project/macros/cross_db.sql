-- Dialect shims. Only two functions differ between DuckDB and BigQuery in
-- this project, so porting is a config change, not a rewrite.

{% macro parse_mixed_date(col) %}
    {#- CRM exports emit ISO (YYYY-MM-DD) or DD/MM/YYYY. Try both, null otherwise. -#}
    {% if target.type == 'duckdb' %}
        coalesce(
            try_cast({{ col }} as date),
            try_strptime({{ col }}, '%d/%m/%Y')::date
        )
    {% elif target.type == 'bigquery' %}
        coalesce(
            safe_cast({{ col }} as date),
            safe.parse_date('%d/%m/%Y', {{ col }})
        )
    {% else %}
        cast({{ col }} as date)
    {% endif %}
{% endmacro %}


{% macro clean_utm(col) %}
    {#- Normalises injected UTM defects in a PRINCIPLED order rather than by
        maintaining an ever-growing typo list:
          1. trim, lowercase, strip trailing underscores
          2. reverse leetspeak digit substitutions (3->e, 1->i, 0->o)
          3. repair the 'in' -> 'ln' transposition family
          4. only then fall back to a small explicit map for the handful of
             defects that are not rule-expressible (e.g. 'oo' -> 'o')
        Anything still unrecognised keeps its cleaned value and is caught by
        the assert_no_unmapped_utm_source test.
        spark/sessionize.py implements the identical ladder — if you change
        one, change both, and analysis/06_parity_check.py will tell you if
        you forgot. -#}
    case
        when {{ col }} is null then null
        else
            case
                replace(
                    replace(
                        replace(
                            replace(
                                lower(regexp_replace(trim({{ col }}), '_+$', '')),
                            '3', 'e'),
                        '1', 'i'),
                    '0', 'o'),
                'ln', 'in')
                when 'gogle'  then 'google'
                when 'inkedin' then 'linkedin'
                else
                    replace(
                        replace(
                            replace(
                                replace(
                                    lower(regexp_replace(trim({{ col }}), '_+$', '')),
                                '3', 'e'),
                            '1', 'i'),
                        '0', 'o'),
                    'ln', 'in')
            end
    end
{% endmacro %}


{% macro safe_divide(num, den) %}
    case when coalesce({{ den }}, 0) = 0 then null
         else cast({{ num }} as double) / cast({{ den }} as double) end
{% endmacro %}
