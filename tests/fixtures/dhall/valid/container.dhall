let H = ../../../../dhall/package.dhall

in  H.config
      { project = "demo"
      , substrates =
        [ H.entry
            H.Substrate.LinuxCpu
            (H.Model.Container H.Container::{ dockerfile = "docker/demo.Dockerfile" })
        ]
      }
