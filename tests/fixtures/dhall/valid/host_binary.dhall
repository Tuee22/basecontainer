let H = ../../../../dhall/package.dhall

in  H.config
      { project = "demo"
      , substrates =
        [ H.entry
            H.Substrate.LinuxCpu
            ( H.Model.HostBinary
                H.HostBinary::{
                , build = H.Build::{
                  , cabal =
                      "cabal install --installdir .build --install-method=copy --overwrite-policy=always exe:demo"
                  }
                , handoff = H.Handoff::{
                  , up = ".build/demo cluster up"
                  , down = ".build/demo cluster down"
                  }
                }
            )
        ]
      }
