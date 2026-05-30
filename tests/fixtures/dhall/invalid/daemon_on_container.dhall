-- A Container has no `daemon` field, so this is a Dhall type error.
let H = ../../../../dhall/package.dhall

in  H.config
      { project = "demo"
      , substrates =
        [ H.entry
            H.Substrate.LinuxCpu
            ( H.Model.Container
                H.Container::{ dockerfile = "d", daemon = ".build/demo serve" }
            )
        ]
      }
