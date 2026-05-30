-- HostDaemon requires `daemon`; omitting it is a Dhall type error.
let H = ../../../../dhall/package.dhall

in  H.config
      { project = "demo"
      , substrates =
        [ H.entry
            H.Substrate.AppleSilicon
            ( H.Model.HostDaemon
                H.HostDaemon::{ build = H.Build::{ cabal = "cabal install exe:demo" } }
            )
        ]
      }
