<!-- gamma_manager (FREE) | role=critic lane=ollama::qwen3:14b elapsed=17.138s | action=Open `analysis/autopsies/2026-09-04.md` -->
<!-- reason: Contender sweep looks complete per the tail note; ranking/critique of recent work is the right lane, and this is the freshest unverified hypothesis in queue. Recent 8 fires are 7x critic/strategist — rotating target to the autopsy claim specifically, not re-critiquing the sweep. -->

The load-bearing assumption is (1): **Is `sum_stop_cost` a *gross* cost-of-stops figure or net of credits received?** If `sum_stop_cost` is gross (i.e., includes all stop losses without subtracting credits from partial fills or other offsets), the 15/30 'dominated' count conflates unavoidable gap-through stops (e.g., market gaps triggering stops) with rule-path stops (e.g., stops triggered by trade logic). This would misrepresent the severity of exit-shape issues, as gross costs exaggerate losses from rule-path stops while ignoring credits that might reduce net impact. The claim’s conclusion hinges on `sum_stop_cost` being a net figure; if it’s gross, the 15/30 ratio and the -225 net PNL comparison are invalid.  

Relevant lines:  
> "sum_stop_cost=8398.55 vs window_net_pnl=-225 over 30 trades, n_dominated=15"  
> "exit_shape_dominated: ..."  

If `sum_stop_cost` is *net* (i.e., includes credits), the 15/30 'dominated' count and the -225 net PNL comparison are valid. If it’s *gross*, the conclusion flips: the 15/30 ratio overstates exit-shape dominance, and the -225 net PNL may not reflect true losses.  

Assumption (2) is secondary: `window_n=30` may not distinguish 'exit dominated' from 'one bad session' (e.g., if -225 is from a single session). However, (1) directly invalidates the core comparison between `sum_stop_cost` and `window_net_pnl`.