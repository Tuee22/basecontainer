-- A HostBinary has no `mounts` field, so this is a Dhall type error.
let H = ../../../../dhall/package.dhall

in  H.config
      { project = "demo"
      , substrates =
        [ H.entry
            H.Substrate.LinuxCpu
            ( H.Model.HostBinary
                H.HostBinary::{
                , build = H.Build::{ cabal = "cabal install exe:demo" }
                , handoff = H.Handoff::{ up = ".build/demo up", down = ".build/demo down" }
                , mounts = [] : List H.Mount.Type
                }
            )
        ]
      }
