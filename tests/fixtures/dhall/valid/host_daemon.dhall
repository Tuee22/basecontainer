let H = ../../../../dhall/package.dhall

in  H.config
      { project = "demo"
      , substrates =
        [ H.entry
            H.Substrate.AppleSilicon
            ( H.Model.HostDaemon
                H.HostDaemon::{
                , build = H.Build::{
                  , cabal = "cabal install --installdir .build exe:demo"
                  , host = H.HostReqs::{ ghc = True, tart = True, metal = True }
                  }
                , daemon = ".build/demo inference --serve"
                }
            )
        ]
      }
